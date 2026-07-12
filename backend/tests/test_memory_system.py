"""记忆系统测试 — 用真实 DeepSeek API 测画像构建，不生图

测试范围：
  1. load_user_context — 不同信件数量下的上下文加载
  2. build_profile — 真实 LLM 从 5 封信提取画像
  3. _format_user_context — prompt 注入格式
  4. Pipeline 集成 — user_context 流入分析和诗歌生成
  5. upsert 和 LLM 失败降级

不生图、不走网络搜索、text LLM 用真实 DeepSeek API。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base, Hometown, Letter, PastSelfProfile, User

# ── 加载 .env 中的 DEEPSEEK_API_KEY ──
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# ── 测试结果 ──
_failed = 0
_passed = 0


def check(name: str, actual, expected) -> None:
    global _passed, _failed
    if actual == expected:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ {name}")
        print(f"     expected: {expected!r}")
        print(f"     actual:   {actual!r}")


def check_ok(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ {name}  {detail}")


def check_contains(name: str, haystack: str, needle: str) -> None:
    global _passed, _failed
    if needle in haystack:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ {name}  '{needle}' not in: {haystack[:120]}...")


# ── Mock LLM（不花钱的测试用）──
class MockLLM:
    def __init__(self, response: str = "") -> None:
        self.call_count = 0
        self.last_system = ""
        self.last_user_msg = ""
        self._response = response or json.dumps({
            "summary": "这是一个安静念旧的人，在黄昏时分想起大学时光。",
            "latent_place_affinities": [{"name": "武汉大学"}, {"name": "操场"}],
            "sensory_biases": [{"name": "黄昏的光"}, {"name": "蝉鸣"}],
            "identity_signals": [{"name": "念旧"}, {"name": "安静"}],
            "recent_memory_signals": [{"name": "常提大学"}],
        }, ensure_ascii=False)

    def chat(self, system: str, user_msg: str,
             temperature: float = 0.4, max_tokens: int = 600) -> str:
        self.call_count += 1
        self.last_system = system
        self.last_user_msg = user_msg
        return self._response


# ── 测试工具 ──
async def _make_db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker()


async def _make_user(db: AsyncSession, day: int = 0) -> User:
    user = User(username="test", hashed_password="x", current_day=day)
    db.add(user)
    await db.flush()
    ht = Hometown(user_id=user.id, province="湖北", city="武汉",
                  county="洪山", hometown_name="武汉洪山")
    db.add(ht)
    await db.flush()
    return user


async def _add_letter(db: AsyncSession, uid: int, text: str,
                      place: str = "", mood: str = "") -> Letter:
    lt = Letter(user_id=uid, text=text, place=place, mood=mood,
                timestamp=datetime.now(timezone.utc))
    db.add(lt)
    await db.flush()
    return lt


# ═══════════════════════════════════════════════
# 1. load_user_context 基础测试
# ═══════════════════════════════════════════════
async def test_load_context_empty():
    print("\n1️⃣  load_user_context — 无信件，返回空上下文")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db)
    ctx = await MemoryService().load_user_context(db, user.id)

    check("recent_letters=[]", ctx["recent_letters"], [])
    check("profile_summary=''", ctx["profile_summary"], "")
    check("profile=None", ctx["profile"], None)


async def test_load_context_with_letters():
    print("\n2️⃣  load_user_context — 6封信，只返回最近3封")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db)

    for i in range(6):
        await _add_letter(db, user.id, f"第{i+1}封信的内容在这里。", f"地点{i}", f"情绪{i}")

    ctx = await MemoryService().load_user_context(db, user.id)

    check("3封", len(ctx["recent_letters"]), 3)
    check_ok("最新的是第6封", ctx["recent_letters"][-1].startswith("第6封"))
    check_ok("不含第1封", not any("第1封" in r for r in ctx["recent_letters"]))
    check("无画像", ctx["profile_summary"], "")


# ═══════════════════════════════════════════════
# 2. build_profile 少于3封 → 跳过
# ═══════════════════════════════════════════════
async def test_build_profile_skip():
    print("\n3️⃣  build_profile — 只有2封信，跳过，LLM不调用")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db)
    await _add_letter(db, user.id, "信1", "武汉", "平静")
    await _add_letter(db, user.id, "信2", "操场", "怀念")

    mock = MockLLM()
    await MemoryService().build_profile(db, user.id, mock)

    check("LLM 未调用", mock.call_count, 0)
    result = await db.execute(select(PastSelfProfile).where(PastSelfProfile.user_id == user.id))
    check("未写入", result.scalar_one_or_none(), None)


# ═══════════════════════════════════════════════
# 3. build_profile — 真实 DeepSeek API
# ═══════════════════════════════════════════════
async def test_build_profile_real_llm():
    print("\n4️⃣  build_profile — 真实 DeepSeek 从 5 封信构建画像（会花钱，约 ¥0.01）")
    from services.memory_service import MemoryService
    from services.llm_service import LlmService

    db = await _make_db()
    user = await _make_user(db)

    letters = [
        ("武汉的夏天热得让人烦躁，只有傍晚起了风才愿意出门。蝉鸣声一直响到天黑。",
         "武汉", "烦躁"),
        ("今天路过华中科技大学，梧桐树还是那么高，叶子沙沙响。突然很想念大学时光。",
         "华中科技大学", "怀念"),
        ("东九楼下的石阶，黄昏的光斜斜地照下来，学生们三三两两走过。那里总是很安静。",
         "东九教学楼", "平静"),
        ("食堂的番茄鸡蛋面还是那个味道，阿姨的手艺一点没变。我坐下来慢慢吃完了。",
         "食堂", "温暖"),
        ("操场边的夕阳美得让人想哭。我坐在看台上看了很久，直到天黑。那时候的烦恼现在想来都不算什么。",
         "操场", "感动"),
    ]
    for text, place, mood in letters:
        await _add_letter(db, user.id, text, place, mood)

    try:
        llm = LlmService()
    except Exception as e:
        print(f"  ⚠️  无法创建 LlmService: {e}，跳过真实 LLM 测试")
        return

    await MemoryService().build_profile(db, user.id, llm)

    # 验证 PastSelfProfile
    result = await db.execute(
        select(PastSelfProfile).where(PastSelfProfile.user_id == user.id)
    )
    psp = result.scalar_one_or_none()
    check_ok("PastSelfProfile 已创建", psp is not None)

    if psp:
        check_ok("summary 非空且>20字", len(psp.summary) > 20,
                 f"summary={psp.summary[:60]}...")
        print(f"\n  📝 画像 summary: {psp.summary}")
        print(f"  📍 地点: {[p['name'] for p in psp.latent_place_affinities]}")
        print(f"  👁️  感官: {[s['name'] for s in psp.sensory_biases]}")
        print(f"  🧠 特质: {[s['name'] for s in psp.identity_signals]}")
        print(f"  🔔 信号: {[s['name'] for s in psp.recent_memory_signals]}")

    # 再次加载上下文
    ctx = await MemoryService().load_user_context(db, user.id)
    check_ok("有画像摘要", bool(ctx["profile_summary"]))
    check_ok("有画像 dict", ctx["profile"] is not None)
    check("3封近期信", len(ctx["recent_letters"]), 3)


# ═══════════════════════════════════════════════
# 4. upsert 测试
# ═══════════════════════════════════════════════
async def test_build_profile_upsert():
    print("\n5️⃣  build_profile — upsert，第二次写入不产生重复行")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db)

    for i in range(5):
        await _add_letter(db, user.id, f"初始信{i+1}", "旧地点", "平静")

    # 第一次
    mock1 = MockLLM()
    await MemoryService().build_profile(db, user.id, mock1)
    check("第1次构建 LLM被调用", mock1.call_count, 1)

    # 再加 5 封新信
    for i in range(5):
        await _add_letter(db, user.id, f"第二阶段的信{i+1}", "新地点", "兴奋")

    # 第二次 — LLM 看到了新信
    mock2 = MockLLM()
    await MemoryService().build_profile(db, user.id, mock2)
    check("第2次也成功", mock2.call_count, 1)
    check_ok("LLM收到新地点", "新地点" in mock2.last_user_msg)

    # 只有一条记录
    result = await db.execute(select(PastSelfProfile).where(PastSelfProfile.user_id == user.id))
    check("PastSelfProfile 仅1行", len(result.scalars().all()), 1)


# ═══════════════════════════════════════════════
# 5. LLM 失败降级
# ═══════════════════════════════════════════════
async def test_build_profile_llm_failure():
    print("\n6️⃣  build_profile — LLM 调用失败时不崩溃、不写入")

    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db)

    for i in range(5):
        await _add_letter(db, user.id, "测试信", "武汉", "平静")

    class FailingLLM:
        def chat(self, *a, **kw):
            raise RuntimeError("API 超时")

    await MemoryService().build_profile(db, user.id, FailingLLM())

    result = await db.execute(select(PastSelfProfile).where(PastSelfProfile.user_id == user.id))
    check("未写入任何行", result.scalar_one_or_none(), None)


# ═══════════════════════════════════════════════
# 6. _format_user_context
# ═══════════════════════════════════════════════
async def test_format_context():
    print("\n7️⃣  _format_user_context — 各种组合的注入文本格式")

    from services.letter_analysis_service import LetterAnalysisService as LAS

    # 画像 + 信件
    ctx = {"profile_summary": "念旧的人。", "recent_letters": ["信A", "信B"]}
    out = LAS._format_user_context(ctx)
    check_ok("画像在前", out.index("用户画像") < out.index("最近写过的信"))
    check_contains("含信A", out, "信A")

    # 仅画像
    out2 = LAS._format_user_context({"profile_summary": "安静。", "recent_letters": []})
    check_contains("仅画像", out2, "用户画像")
    check_ok("无信件段", "最近写过" not in out2)

    # 仅信件
    out3 = LAS._format_user_context({"profile_summary": "", "recent_letters": ["X"]})
    check_contains("仅信件", out3, "最近写过")
    check_ok("无画像段", "用户画像" not in out3)

    # 空
    check("空→空", LAS._format_user_context({}), "")


# ═══════════════════════════════════════════════
# 7. PoemService — user_context 注入正文
# ═══════════════════════════════════════════════
async def test_poem_body_with_profile():
    print("\n8️⃣  PoemService — 有画像时正文 prompt 包含性格提示")

    from services.poem_service import PoemService

    mock = MockLLM()
    svc = PoemService(mock)

    # 无上下文
    svc.generate_body({"name": "故乡"}, "短诗", "信内容")
    call_without = mock.last_user_msg
    check_ok("无画像时不含性格", "写信人的性格画像" not in call_without)

    # 有画像
    ctx = {"profile_summary": "安静念旧，喜欢黄昏。", "recent_letters": []}
    svc.generate_body({"name": "故乡"}, "短诗", "信", user_context=ctx)
    call_with = mock.last_user_msg
    check_contains("含画像", call_with, "写信人的性格画像")
    check_contains("含性格关键词", call_with, "安静念旧")
    check_contains("含语气指令", call_with, "符合这个性格的语气")

    # 标题
    svc.generate_title({"name": "故乡"}, "短诗", user_context=ctx)
    check_contains("标题含画像", mock.last_user_msg, "安静念旧")


# ═══════════════════════════════════════════════
# 8. Pipeline 集成 — user_context 全链路
# ═══════════════════════════════════════════════
async def test_pipeline_context_flow():
    print("\n9️⃣  Pipeline 集成 — user_context 流入分析 → 正文全链路")

    from services.memory_service import MemoryService
    from services.letter_analysis_service import LetterAnalysisService
    from services.poem_service import PoemService

    db = await _make_db()
    user = await _make_user(db, day=4)

    # 写入历史信件
    for i in range(5):
        await _add_letter(db, user.id,
                          f"历史信{i+1}：武大樱花开了，风一吹像粉色的雪。想念那里的图书馆。",
                          "武汉大学", "怀念")

    # 加载上下文
    ctx = await MemoryService().load_user_context(db, user.id)
    check("有3封近期信", len(ctx["recent_letters"]), 3)

    # 先建画像，让后续 generate_body 能拿到 profile_summary
    profile_mock = MockLLM()
    await MemoryService().build_profile(db, user.id, profile_mock)
    ctx = await MemoryService().load_user_context(db, user.id)
    check_ok("现在有画像摘要", bool(ctx["profile_summary"]))

    # 用 mock LLM 测分析
    mock = MockLLM(json.dumps({
        "visual_themes": ["樱花", "图书馆", "春风"],
        "emotional_tone": "怀念/温暖",
        "scene_type": "school_gate",
        "search_keywords": ["武汉大学 樱花"],
        "core_place": "武汉大学",
        "image_prompt": "test",
    }, ensure_ascii=False))

    analyzer = LetterAnalysisService(mock)
    analysis = analyzer.analyze_letter_deep(
        letter_text="今天又梦到了樱花。",
        place_hint="武汉大学",
        mood_hint="怀念",
        user_context=ctx,
    )
    check_contains("analys→core_place", analysis["core_place"], "武汉大学")

    # 验证 LLM 收到了上下文
    check_ok("LLM prompt 含近期信内容",
             "武大樱花" in mock.last_user_msg or "想念" in mock.last_user_msg,
             f"hint: {mock.last_user_msg[:150]}")

    # 正文生成
    mock2 = MockLLM()
    svc = PoemService(mock2)
    svc.generate_body({"name": "武汉大学"}, "樱花落下的短诗", "梦到樱花",
                      analysis=analysis, user_context=ctx)
    check_ok("正文 LLM 收到画像", "写信人的性格画像" in mock2.last_user_msg)


# ═══════════════════════════════════════════════
async def main():
    global _passed, _failed
    print("=" * 60)
    print("  记忆系统完整测试")
    print("  Mock LLM + 真实 DeepSeek API（仅画像构建）")
    print("  不生图 · 不走搜索 · 总花费 ≈ ¥0.01")
    print("=" * 60)

    tests = [
        test_load_context_empty,
        test_load_context_with_letters,
        test_build_profile_skip,
        test_build_profile_real_llm,
        test_build_profile_upsert,
        test_build_profile_llm_failure,
        test_format_context,
        test_poem_body_with_profile,
        test_pipeline_context_flow,
    ]

    for t in tests:
        try:
            await t()
        except Exception as e:
            _failed += 1
            print(f"\n  💥 {t.__name__} CRASHED: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"  {_passed} 通过, {_failed} 失败 (共 {_passed + _failed})")
    print(f"{'=' * 60}")

    if _failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
