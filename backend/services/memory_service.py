"""记忆服务 — 按每 5 封信沉淀 summary / memory，并供下游 prompt 使用"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Letter, LetterMemory, LetterSummary, PastSelfProfile
from services.prompt_service import get_prompt

logger = logging.getLogger(__name__)

BATCH_SIZE = 5
MAX_CONTEXT_SUMMARIES = 3
MAX_CONTEXT_MEMORIES = 3
MAX_CONTEXT_LETTERS = 5

class MemoryService:
    async def load_user_context(
        self, db: AsyncSession, user_id: int
    ) -> dict:
        """加载写信所需上下文：最近信件 + 阶段记忆总结 + 长期画像"""
        recent_letters = await self._load_recent_letters(db, user_id, MAX_CONTEXT_LETTERS)
        summaries = await self._load_recent_summaries(db, user_id, MAX_CONTEXT_SUMMARIES)
        memories = await self._load_recent_memories(db, user_id, MAX_CONTEXT_MEMORIES)
        tail_letters = await self._load_tail_letters(db, user_id)

        result = await db.execute(
            select(PastSelfProfile).where(PastSelfProfile.user_id == user_id)
        )
        profile_row = result.scalar_one_or_none()

        profile_summary = ""
        profile = None
        if profile_row and profile_row.summary:
            profile_summary = profile_row.summary
            profile = {
                "summary": profile_row.summary,
                "latent_place_affinities": profile_row.latent_place_affinities or [],
                "sensory_biases": profile_row.sensory_biases or [],
                "identity_signals": profile_row.identity_signals or [],
                "recent_memory_signals": profile_row.recent_memory_signals or [],
            }

        logger.info(
            "loaded user memory context: recent_letters=%d summaries=%d memories=%d tail=%d profile=%s",
            len(recent_letters), len(summaries), len(memories), len(tail_letters),
            "yes" if profile_summary else "no",
        )
        return {
            "recent_letters": recent_letters,
            "recent_summaries": summaries,
            "recent_memories": memories,
            "tail_letters": tail_letters,
            "profile_summary": profile_summary,
            "profile": profile,
        }

    async def maybe_build_batch_memory(
        self, db: AsyncSession, user_id: int, llm
    ) -> None:
        """当用户信件总数达到 5 的倍数时，为这一批 5 封信生成 summary/memory"""
        result = await db.execute(
            select(func.count(Letter.id)).where(Letter.user_id == user_id)
        )
        total_letters = int(result.scalar() or 0)
        if total_letters == 0 or total_letters % BATCH_SIZE != 0:
            logger.info("batch memory skipped: total_letters=%d", total_letters)
            return

        batch_no = total_letters // BATCH_SIZE
        result = await db.execute(
            select(LetterSummary).where(
                LetterSummary.user_id == user_id,
                LetterSummary.batch_no == batch_no,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("batch memory skipped: batch_no=%d already exists", batch_no)
            return

        result = await db.execute(
            select(Letter)
            .where(Letter.user_id == user_id)
            .order_by(Letter.timestamp.desc(), Letter.id.desc())
            .limit(BATCH_SIZE)
        )
        letters = list(reversed(result.scalars().all()))
        if len(letters) != BATCH_SIZE:
            logger.warning("batch memory skipped: expected 5 letters, got %d", len(letters))
            return

        payload = self._build_batch_payload(letters)
        try:
            raw = llm.chat(
                get_prompt("batch_memory"),
                payload,
                temperature=0.4,
                max_tokens=900,
            )
            data = self._parse_json(raw)
        except Exception as e:
            logger.warning("batch memory LLM call failed: %s", e)
            return

        if not data:
            return

        now = datetime.now(timezone.utc)
        summary = LetterSummary(
            user_id=user_id,
            batch_no=batch_no,
            start_letter_id=letters[0].id,
            end_letter_id=letters[-1].id,
            letter_count=len(letters),
            summary_text=data.get("summary_text", ""),
            source_letter_ids=[lt.id for lt in letters],
            created_at=now,
            updated_at=now,
        )
        db.add(summary)
        await db.flush()

        memory_data = data.get("memory", {}) or {}
        memory = LetterMemory(
            user_id=user_id,
            summary_id=summary.id,
            memory_overview=memory_data.get("memory_overview", ""),
            emotion_signals=memory_data.get("emotion_signals", []),
            place_signals=memory_data.get("place_signals", []),
            theme_signals=memory_data.get("theme_signals", []),
            people_signals=memory_data.get("people_signals", []),
            sensory_signals=memory_data.get("sensory_signals", []),
            created_at=now,
            updated_at=now,
        )
        db.add(memory)
        await db.flush()
        logger.info("built letter summary/memory: user=%s batch=%s", user_id, batch_no)

    async def rebuild_profile_from_batches(
        self, db: AsyncSession, user_id: int, llm
    ) -> None:
        """基于历史批次 summary/memory 更新长期画像"""
        result = await db.execute(
            select(LetterSummary, LetterMemory)
            .outerjoin(LetterMemory, LetterMemory.summary_id == LetterSummary.id)
            .where(LetterSummary.user_id == user_id)
            .order_by(LetterSummary.batch_no.asc())
        )
        rows = result.all()
        if not rows:
            logger.info("profile rebuild skipped: no batch summaries")
            return

        parts = []
        for summary, memory in rows:
            parts.append(f"第{summary.batch_no}批总结：{summary.summary_text}")
            if memory:
                if memory.memory_overview:
                    parts.append(f"第{summary.batch_no}批记忆概览：{memory.memory_overview}")
                for label, values in (
                    ("情绪", memory.emotion_signals or []),
                    ("地点", memory.place_signals or []),
                    ("主题", memory.theme_signals or []),
                    ("人物", memory.people_signals or []),
                    ("感官", memory.sensory_signals or []),
                ):
                    names = [item.get("name", "") for item in values if item.get("name")]
                    if names:
                        parts.append(f"第{summary.batch_no}批{label}：{'、'.join(names)}")

        try:
            raw = llm.chat(
                get_prompt("profile"),
                "\n".join(parts),
                temperature=0.4,
                max_tokens=700,
            )
            data = self._parse_json(raw)
        except Exception as e:
            logger.warning("profile rebuild LLM call failed: %s", e)
            return

        if not data:
            return

        result = await db.execute(
            select(PastSelfProfile).where(PastSelfProfile.user_id == user_id)
        )
        existing = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing:
            existing.summary = data.get("summary", "")
            existing.latent_place_affinities = data.get("latent_place_affinities", [])
            existing.sensory_biases = data.get("sensory_biases", [])
            existing.identity_signals = data.get("identity_signals", [])
            existing.recent_memory_signals = data.get("recent_memory_signals", [])
            existing.updated_at = now
        else:
            db.add(PastSelfProfile(
                user_id=user_id,
                summary=data.get("summary", ""),
                latent_place_affinities=data.get("latent_place_affinities", []),
                sensory_biases=data.get("sensory_biases", []),
                identity_signals=data.get("identity_signals", []),
                recent_memory_signals=data.get("recent_memory_signals", []),
                updated_at=now,
            ))
        await db.flush()
        logger.info("rebuilt long-term profile from batch summaries: user=%s", user_id)

    def format_context_for_prompt(self, user_context: dict) -> str:
        parts = []

        # 1) 最近 5 封信（最直接的上下文）
        recent = user_context.get("recent_letters", [])
        if recent:
            parts.append("用户最近写过的信：")
            for i, lt in enumerate(recent, 1):
                loc = f"，地点：{lt['place']}" if lt.get("place") else ""
                mood = f"，情绪：{lt['mood']}" if lt.get("mood") else ""
                parts.append(f"  {i}. {lt['text']}{loc}{mood}")

        # 2) 阶段总结（LLM 浓缩后的回顾）
        summaries = user_context.get("recent_summaries", [])
        if summaries:
            parts.append("最近阶段总结：")
            for item in summaries:
                parts.append(f"  - 第{item['batch_no']}批：{item['summary_text']}")

        # 3) 阶段记忆信号（地点/情绪/主题/人物/感官）
        memories = user_context.get("recent_memories", [])
        if memories:
            parts.append("最近阶段记忆：")
            for item in memories:
                line = [f"  - 第{item['batch_no']}批"]
                if item.get("memory_overview"):
                    line.append(item["memory_overview"])
                signal_parts = []
                for key, label in (
                    ("emotion_signals", "情绪"),
                    ("place_signals", "地点"),
                    ("theme_signals", "主题"),
                    ("people_signals", "人物"),
                    ("sensory_signals", "感官"),
                ):
                    names = [v.get("name", "") for v in item.get(key, []) if v.get("name")]
                    if names:
                        signal_parts.append(f"{label}：{'、'.join(names)}")
                if signal_parts:
                    line.append("；".join(signal_parts))
                parts.append(" ".join(line))

        # 4) 未归档的尾部信件（还没满 5 封的新来信）
        tail_letters = user_context.get("tail_letters", [])
        if tail_letters:
            parts.append("当前阶段尚未归档的来信：")
            for i, text in enumerate(tail_letters, 1):
                parts.append(f"  {i}. {text[:200]}")

        # 5) 长期画像
        if user_context.get("profile_summary"):
            parts.append(f"长期画像：{user_context['profile_summary']}")

        return "\n".join(parts) if parts else ""

    async def _load_recent_summaries(self, db: AsyncSession, user_id: int, limit: int) -> list[dict]:
        result = await db.execute(
            select(LetterSummary)
            .where(LetterSummary.user_id == user_id)
            .order_by(LetterSummary.batch_no.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
        return [
            {
                "batch_no": row.batch_no,
                "summary_text": row.summary_text,
            }
            for row in rows if row.summary_text
        ]

    async def _load_recent_memories(self, db: AsyncSession, user_id: int, limit: int) -> list[dict]:
        result = await db.execute(
            select(LetterSummary, LetterMemory)
            .join(LetterMemory, LetterMemory.summary_id == LetterSummary.id)
            .where(LetterSummary.user_id == user_id)
            .order_by(LetterSummary.batch_no.desc())
            .limit(limit)
        )
        rows = list(reversed(result.all()))
        return [
            {
                "batch_no": summary.batch_no,
                "memory_overview": memory.memory_overview,
                "emotion_signals": memory.emotion_signals or [],
                "place_signals": memory.place_signals or [],
                "theme_signals": memory.theme_signals or [],
                "people_signals": memory.people_signals or [],
                "sensory_signals": memory.sensory_signals or [],
            }
            for summary, memory in rows
        ]

    async def _load_tail_letters(self, db: AsyncSession, user_id: int) -> list[str]:
        result = await db.execute(
            select(func.count(Letter.id)).where(Letter.user_id == user_id)
        )
        total_letters = int(result.scalar() or 0)
        tail_count = total_letters % BATCH_SIZE
        if tail_count == 0:
            return []

        result = await db.execute(
            select(Letter)
            .where(Letter.user_id == user_id)
            .order_by(Letter.timestamp.desc(), Letter.id.desc())
            .limit(tail_count)
        )
        letters = list(reversed(result.scalars().all()))
        return [lt.text[:200] for lt in letters if (lt.text or "").strip()]

    async def _load_recent_letters(
        self, db: AsyncSession, user_id: int, limit: int
    ) -> list[dict]:
        """加载用户最近 N 封信件（含地点和情绪）"""
        result = await db.execute(
            select(Letter)
            .where(Letter.user_id == user_id)
            .order_by(Letter.timestamp.desc(), Letter.id.desc())
            .limit(limit)
        )
        letters = list(reversed(result.scalars().all()))
        return [
            {
                "id": lt.id,
                "text": (lt.text or "").strip().replace("\n", " ")[:300],
                "place": lt.place or "",
                "mood": lt.mood or "",
                "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
            }
            for lt in letters
        ]

    def _build_batch_payload(self, letters: list[Letter]) -> str:
        parts = []
        for i, lt in enumerate(letters, 1):
            snippet = (lt.text or "").strip().replace("\n", " ")[:300]
            parts.append(
                f"第{i}封信（id={lt.id}，地点：{lt.place or '未知'}，情绪：{lt.mood or '未知'}）：\n{snippet}"
            )
        return "\n\n".join(parts)

    def _parse_json(self, raw: str) -> dict | None:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("failed to parse memory/profile JSON")
            return None
