"""批次记忆系统测试

测试范围：
1. 每个用户每满 5 封信，生成 1 条 summary 和 1 条 memory
2. 非 5 倍数时不触发
3. 同一批次不会重复生成
4. 写信上下文会读取 summary / memory / 尾部未归档信件
5. 长期画像会从批次 summary 重建
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

from db.models import Base, Hometown, Letter, LetterMemory, LetterSummary, PastSelfProfile, User

_failed = 0
_passed = 0


def check(name: str, actual, expected) -> None:
    global _passed, _failed
    if actual == expected:
        _passed += 1
        print(f"  PASS {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}")
        print(f"     expected: {expected!r}")
        print(f"     actual:   {actual!r}")


def check_ok(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {detail}")


def check_contains(name: str, haystack: str, needle: str) -> None:
    global _passed, _failed
    if needle in haystack:
        _passed += 1
        print(f"  PASS {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} missing={needle!r}")


class MockBatchLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user_msg: str, **kwargs) -> str:
        self.calls.append((system, user_msg))
        if "阶段性书信总结" in system or "长期画像" in system:
            return json.dumps({
                "summary": "这是一个会反复回望校园、黄昏和旧时情绪的人。",
                "latent_place_affinities": [{"name": "校园"}],
                "sensory_biases": [{"name": "黄昏的光"}],
                "identity_signals": [{"name": "念旧"}],
                "recent_memory_signals": [{"name": "最近常写校园"}],
            }, ensure_ascii=False)
        return json.dumps({
            "summary_text": "这五封信都在围绕校园、黄昏和旧时心绪展开，情绪从试探慢慢走向怀念。",
            "memory": {
                "memory_overview": "这一阶段最明显的是校园场景、黄昏光线和对过去关系的反复回看。",
                "emotion_signals": [{"name": "怀念"}, {"name": "迟疑"}],
                "place_signals": [{"name": "校园"}, {"name": "操场"}],
                "theme_signals": [{"name": "旧时关系"}, {"name": "大学时光"}],
                "people_signals": [{"name": "喜欢的人"}],
                "sensory_signals": [{"name": "黄昏的光"}],
            },
        }, ensure_ascii=False)


async def _make_db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker()


async def _make_user(db: AsyncSession, username: str = "test", day: int = 0) -> User:
    user = User(username=username, hashed_password="x", current_day=day)
    db.add(user)
    await db.flush()
    db.add(Hometown(user_id=user.id, province="湖南", city="郴州", county="资兴", hometown_name="资兴"))
    await db.flush()
    return user


async def _add_letter(db: AsyncSession, uid: int, text: str, place: str = "", mood: str = "") -> Letter:
    lt = Letter(
        user_id=uid,
        text=text,
        place=place,
        mood=mood,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(lt)
    await db.flush()
    return lt


async def test_batch_trigger_exactly_on_five():
    print("\n1) 满 5 封时生成 summary + memory")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db)
    llm = MockBatchLLM()

    for i in range(5):
        await _add_letter(db, user.id, f"第{i+1}封信，还是想起校园和黄昏。", "校园", "怀念")

    svc = MemoryService()
    await svc.maybe_build_batch_memory(db, user.id, llm)

    result = await db.execute(select(LetterSummary).where(LetterSummary.user_id == user.id))
    summaries = result.scalars().all()
    check("summary数量", len(summaries), 1)
    if summaries:
        check("batch_no=1", summaries[0].batch_no, 1)
        check("letter_count=5", summaries[0].letter_count, 5)

    result = await db.execute(select(LetterMemory).where(LetterMemory.user_id == user.id))
    memories = result.scalars().all()
    check("memory数量", len(memories), 1)
    if memories:
        check_contains("有情绪信号", json.dumps(memories[0].emotion_signals, ensure_ascii=False), "怀念")


async def test_batch_skip_on_non_multiple():
    print("\n2) 非 5 倍数不生成")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db, username="u2")
    llm = MockBatchLLM()

    for i in range(4):
        await _add_letter(db, user.id, f"第{i+1}封", "学校", "平静")

    await MemoryService().maybe_build_batch_memory(db, user.id, llm)
    result = await db.execute(select(LetterSummary).where(LetterSummary.user_id == user.id))
    check("summary数量=0", len(result.scalars().all()), 0)


async def test_batch_idempotent():
    print("\n3) 同一批次不会重复生成")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db, username="u3")
    llm = MockBatchLLM()

    for i in range(5):
        await _add_letter(db, user.id, f"第{i+1}封", "操场", "怀念")

    svc = MemoryService()
    await svc.maybe_build_batch_memory(db, user.id, llm)
    await svc.maybe_build_batch_memory(db, user.id, llm)

    result = await db.execute(select(LetterSummary).where(LetterSummary.user_id == user.id))
    check("仍然只有1条summary", len(result.scalars().all()), 1)


async def test_context_reads_summary_memory_and_tail():
    print("\n4) 上下文读取 summary/memory/尾部信件")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db, username="u4")
    llm = MockBatchLLM()
    svc = MemoryService()

    for i in range(5):
        await _add_letter(db, user.id, f"第一阶段第{i+1}封，想起校园。", "校园", "怀念")
    await svc.maybe_build_batch_memory(db, user.id, llm)
    await svc.rebuild_profile_from_batches(db, user.id, llm)

    for i in range(2):
        await _add_letter(db, user.id, f"尾部第{i+1}封，最近又想起操场。", "操场", "迟疑")

    ctx = await svc.load_user_context(db, user.id)
    check("summary条数", len(ctx["recent_summaries"]), 1)
    check("memory条数", len(ctx["recent_memories"]), 1)
    check("tail_letters条数", len(ctx["tail_letters"]), 2)
    check_ok("有profile_summary", bool(ctx["profile_summary"]))

    formatted = svc.format_context_for_prompt(ctx)
    check_contains("含阶段总结", formatted, "最近阶段总结")
    check_contains("含阶段记忆", formatted, "最近阶段记忆")
    check_contains("含尾部信件", formatted, "当前阶段尚未归档的来信")


async def test_profile_rebuilt_from_batches():
    print("\n5) 长期画像从批次 summary 重建")
    from services.memory_service import MemoryService

    db = await _make_db()
    user = await _make_user(db, username="u5")
    llm = MockBatchLLM()
    svc = MemoryService()

    for i in range(10):
        await _add_letter(db, user.id, f"第{i+1}封，总是提校园、黄昏和旧关系。", "校园", "怀念")
        if (i + 1) % 5 == 0:
            await svc.maybe_build_batch_memory(db, user.id, llm)

    await svc.rebuild_profile_from_batches(db, user.id, llm)

    result = await db.execute(select(PastSelfProfile).where(PastSelfProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    check_ok("画像已生成", profile is not None)
    if profile:
        check_contains("画像summary有内容", profile.summary, "校园")
        check_contains("recent_memory_signals有内容", json.dumps(profile.recent_memory_signals, ensure_ascii=False), "校园")


async def main():
    tests = [
        test_batch_trigger_exactly_on_five,
        test_batch_skip_on_non_multiple,
        test_batch_idempotent,
        test_context_reads_summary_memory_and_tail,
        test_profile_rebuilt_from_batches,
    ]
    for t in tests:
        try:
            await t()
        except Exception as e:
            global _failed
            _failed += 1
            print(f"  CRASH {t.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nRESULT: {_passed} passed, {_failed} failed")
    if _failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
