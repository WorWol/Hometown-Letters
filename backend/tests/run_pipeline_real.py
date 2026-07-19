"""真实管道运行脚本 — 全链路测试

场景: 郴州用户 → 华中科技大学 → "你好，你在学校有找到你喜欢的人吗"
结果: 生成图片保存到桌面
"""
import asyncio
import os
import shutil
import sys
from pathlib import Path

# 确保 backend 在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import upgrade_db, async_session
from db.models import User, Hometown, Postcard, Letter, Landmark
from auth.security import hash_password
from services.llm_service import LlmService
from services.search_service import SearchService
from services.image_service import ImageService
from services.selection_service import SelectionService
from services.poem_service import PoemService
from services.memory_service import MemoryService
from services.pipeline_service import LetterPipeline
from services import image_storage

TEST_USER = "pipe_test_user"
TEST_PASS = "test123"

DESKTOP = Path.home() / "Desktop"
assert DESKTOP.exists(), f"桌面路径不存在: {DESKTOP}"


async def setup_user(db: AsyncSession) -> User:
    """创建或重置测试用户，设置故乡为湖南郴州"""
    # 查已有用户
    result = await db.execute(select(User).where(User.username == TEST_USER))
    user = result.scalar_one_or_none()

    if user:
        print(f"[setup] 已有测试用户 id={user.id}，重置...")
        # 清理旧数据
        for model in [Postcard, Letter, Landmark]:
            await db.execute(delete(model).where(model.user_id == user.id))
        await db.execute(delete(Hometown).where(Hometown.user_id == user.id))
        user.current_day = 0
    else:
        print(f"[setup] 创建测试用户...")
        user = User(username=TEST_USER, hashed_password=hash_password(TEST_PASS), current_day=0)
        db.add(user)

    await db.flush()

    # 设置故乡: 湖南-郴州（不是武汉，测试跨城场景）
    result = await db.execute(select(Hometown).where(Hometown.user_id == user.id))
    h = result.scalar_one_or_none()
    if h:
        h.province = "湖南"
        h.city = "郴州"
        h.county = "资兴"
        h.hometown_name = "湖南郴州资兴"
    else:
        h = Hometown(user_id=user.id, province="湖南", city="郴州", county="资兴", hometown_name="湖南郴州资兴")
        db.add(h)

    await db.flush()
    print(f"[setup] 用户就绪: id={user.id} 故乡=郴州")
    return user


async def main():
    # 初始化 DB
    await upgrade_db()

    # 创建服务
    llm = LlmService()
    search = SearchService()
    image_gen = ImageService()
    selection_svc = SelectionService()  # 不再需要 llm
    poem_svc = PoemService(llm)
    memory_svc = MemoryService()

    pipeline = LetterPipeline(
        llm=llm, search=search, image_gen=image_gen,
        selection_svc=selection_svc, poem_svc=poem_svc, memory_svc=memory_svc,
    )

    async with async_session() as db:
        user = await setup_user(db)

        print()
        print("=" * 60)
        print("  管道启动")
        print("  hometown: 湖南郴州资兴")
        print("  letter:   你好，你在学校有找到你喜欢的人吗")
        print("  hint:     华中科技大学")
        print("  mood:     怀念")
        print("=" * 60)
        print()

        result = await pipeline.process(
            db=db,
            user=user,
            text="你好，你在学校有找到你喜欢的人吗",
            place_hint="华中科技大学",
            mood_hint="怀念",
        )

        await db.commit()

    if not result.get("ok"):
        print(f"\n❌ 管道失败: {result.get('error')}")
        return

    data = result["data"]
    print()
    print("=" * 60)
    print("  管道完成")
    print("=" * 60)
    print(f"  标题:      {data['title']}")
    print(f"  地点:      {data['place']}")
    print(f"  情绪:      {data['mood']}")
    print(f"  明信片正文:")
    print(f"    {data['body']}")
    print(f"  诗:")
    for line in data['poem'].strip().split('\n'):
        print(f"    {line}")
    print()
    print(f"  图片提示词:")
    print(f"    {data['imagePrompt'][:120]}...")
    print(f"  搜索图URL:  {len(data['searchImageUrls'])} 张")

    # 复制图片到桌面
    pc_id = data["id"]
    original_key = image_storage.image_variant_keys(user.id, pc_id)["original"]
    source_url = image_storage.get_image_url(original_key)
    dest = DESKTOP / f"故乡来信_{pc_id}.jpg"

    print()
    if image_storage.settings.storage_backend.lower() == "local":
        source_path = image_storage.IMAGES_DIR / original_key
        if source_path.is_file():
            shutil.copy2(source_path, dest)
            print(f"✅ 图片已复制到桌面: {dest.name}")
            print(f"   大小: {source_path.stat().st_size / 1024:.1f} KB")
            return

    if source_url.startswith("http"):
        print("   下载存储图片到桌面...")
        img_bytes = await ImageService.download_image_bytes(source_url)
        if img_bytes:
            dest.write_bytes(img_bytes)
            print(f"✅ 图片已下载到桌面: {dest.name}")
            print(f"   大小: {len(img_bytes) / 1024:.1f} KB")
        else:
            print("❌ 图片下载失败")
    else:
        print(f"❌ 无可用图片 URL: {source_url}")


if __name__ == "__main__":
    asyncio.run(main())
