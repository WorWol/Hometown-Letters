"""generate_postcard 保存逻辑测试（mock run_letter_agent，测编排层）。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base, Hometown, Postcard, User
from services.letter_agent import LetterAgent


def _patch_storage(monkeypatch):
    """统一 monkeypatch 下载/保存/image_url，避免真 IO。"""
    from services.image_service import ImageService
    from services import letter_agent as letter_agent_mod

    async def fake_download(url):
        if "gen.example.com" in url:
            return b"generated-image-bytes"
        if "pics.example.com" in url or "images.example.com" in url:
            return b"ref-bytes"
        return b"fake"
    monkeypatch.setattr(ImageService, "download_image_bytes", fake_download)
    monkeypatch.setattr(ImageService, "encode_reference_image", lambda data, url: f"data:image/png;base64,{url[:4]}")

    async def fake_save_images(user_id, image_id, data):
        return {"thumb": f"t/{image_id}", "card": f"c/{image_id}", "original": f"o/{image_id}"}

    async def fake_save_ref_images(user_id, image_id, items):
        return [{"key": f"r/{image_id}/{i}", "source_url": it.get("source_url", "")} for i, it in enumerate(items)]

    monkeypatch.setattr(letter_agent_mod, "save_images", fake_save_images)
    monkeypatch.setattr(letter_agent_mod, "save_reference_images", fake_save_ref_images)
    monkeypatch.setattr(letter_agent_mod, "image_url", lambda key: f"/media/{key}")


class MockMemory:
    async def load_user_context(self, db, user_id):
        return {}

    async def maybe_build_batch_memory(self, *a, **k):
        return None

    async def rebuild_profile_from_batches(self, *a, **k):
        return None


def _make_agent():
    return LetterAgent(llm=None, search=None, image_gen=None, memory_svc=MockMemory())


async def test_generate_postcard_saves(monkeypatch):
    """agent 生图后，generate_postcard 下载生成图 + 参考图保存。"""
    _patch_storage(monkeypatch)

    async def fake_run(self, **kwargs):
        return {
            "image_url": "https://gen.example.com/result.webp",
            "image_prompt": "pixel art tokyo fireworks",
            "reference_images": [{"url": "https://pics.example.com/scene.jpg", "role": "scene"}],
            "poem": "诗", "title": "标题", "body": "正文",
            "core_place": "东京隅田川", "generation_place": "东京隅田川",
            "emotional_tone": "怀念", "visual_themes": ["烟花"],
            "_viewed_images": {"https://pics.example.com/scene.jpg": b"scene-data"},
        }
    from services.letter_agent import LetterAgent as LA
    monkeypatch.setattr(LA, "run_letter_agent", fake_run)

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as db:
        user = User(username="test-user", hashed_password="x", current_day=0, postcard_limit=5, postcard_count=0)
        db.add(user)
        await db.flush()
        agent = _make_agent()
        result = await agent.generate_postcard(db, user, "菲比在东京看烟花", "东京隅田川", "怀念")
        await db.commit()

    assert result["ok"] is True, result
    assert result["data"]["imagePrompt"] == "pixel art tokyo fireworks"
    # Postcard 保存 + 参考图
    async with maker() as db:
        pc = await db.scalar(select(Postcard).where(Postcard.user_id == user.id))
        assert pc is not None
        assert pc.image_prompt == "pixel art tokyo fireworks"
        assert len(pc.reference_images) == 1
        assert pc.reference_images[0]["type"] == "scene"
    await engine.dispose()


async def test_no_image_url_does_not_persist(monkeypatch):
    """agent 未生图（image_url 空）时不持久化。"""
    _patch_storage(monkeypatch)

    async def fake_run(self, **kwargs):
        return {
            "image_url": "",
            "image_prompt": "...", "reference_images": [],
            "poem": "", "title": "", "body": "",
            "core_place": "东京", "generation_place": "东京",
            "emotional_tone": "怀念", "visual_themes": [],
            "_viewed_images": {},
        }
    from services.letter_agent import LetterAgent as LA
    monkeypatch.setattr(LA, "run_letter_agent", fake_run)

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as db:
        user = User(username="noimg-user", hashed_password="x", current_day=0, postcard_limit=5, postcard_count=0)
        db.add(user)
        await db.flush()
        agent = _make_agent()
        result = await agent.generate_postcard(db, user, "测试", "东京", "怀念")

    assert result["ok"] is False
    assert "未生图" in result["error"]
    async with maker() as db:
        assert await db.scalar(select(func.count()).select_from(Postcard)) == 0
    await engine.dispose()


async def test_generated_image_download_failure_does_not_persist(monkeypatch):
    """生成图下载失败时不持久化。"""
    from services.image_service import ImageService
    from services import letter_agent as letter_agent_mod

    async def fake_download(url):
        if "gen.example.com" in url:
            return None  # 生成图下载失败
        return b"ref"
    monkeypatch.setattr(ImageService, "download_image_bytes", fake_download)
    monkeypatch.setattr(ImageService, "encode_reference_image", lambda data, url: "data:image/png;base64,ZmFrZQ==")
    async def fake_save_images(user_id, image_id, data):
        return {"thumb": f"t/{image_id}", "card": f"c/{image_id}", "original": f"o/{image_id}"}
    async def fake_save_ref_images(user_id, image_id, items):
        return [{"key": f"r/{image_id}/{i}", "source_url": ""} for i, it in enumerate(items)]
    monkeypatch.setattr(letter_agent_mod, "save_images", fake_save_images)
    monkeypatch.setattr(letter_agent_mod, "save_reference_images", fake_save_ref_images)
    monkeypatch.setattr(letter_agent_mod, "image_url", lambda key: f"/media/{key}")

    async def fake_run(self, **kwargs):
        return {
            "image_url": "https://gen.example.com/result.webp",
            "image_prompt": "...", "reference_images": [],
            "poem": "", "title": "", "body": "",
            "core_place": "东京", "generation_place": "东京",
            "emotional_tone": "怀念", "visual_themes": [],
            "_viewed_images": {},
        }
    from services.letter_agent import LetterAgent as LA
    monkeypatch.setattr(LA, "run_letter_agent", fake_run)

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as db:
        user = User(username="dlfail-user", hashed_password="x", current_day=0, postcard_limit=5, postcard_count=0)
        db.add(user)
        await db.flush()
        agent = _make_agent()
        result = await agent.generate_postcard(db, user, "测试", "东京", "怀念")

    assert result["ok"] is False
    assert "generated image download failed" in result["error"]
    async with maker() as db:
        assert await db.scalar(select(func.count()).select_from(Postcard)) == 0
    await engine.dispose()
