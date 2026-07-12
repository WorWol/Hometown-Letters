"""记忆服务 — 用户画像构建与上下文加载

双层记忆架构：
  - 实时层：最近 N 封信的原文，直接注入 prompt
  - 长期层：PastSelfProfile 结构化画像，每 5 封信更新一次
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Letter, PastSelfProfile

logger = logging.getLogger(__name__)

MAX_RECENT_LETTERS = 3

SYSTEM_PROFILE = """你是一位敏锐的心理观察者，善于从文字中读取一个人的性格。

下面是一个人在不同时间写给故乡的信。请根据这些信的内容，总结这个人的画像。

## 你的任务
1. **summary**：100-200 字的中文总结。格式："这是一个……的人。他/她……"。用温暖、文学化的语言描述这个人的性格、情感模式和内心世界。
2. **latent_place_affinities**：信中反复提到的地点，每项 {"name": "操场"}，最多 5 个
3. **sensory_biases**：这个人对哪些感官细节特别敏感（光线、气味、声音、触感等），每项 {"name": "喜欢黄昏的光"}，最多 5 个
4. **identity_signals**：从信中能读出的身份特征或性格特质，每项 {"name": "安静但念旧"}，最多 4 个
5. **recent_memory_signals**：最近几封信中浮现的主题或情绪倾向，每项 {"name": "最近常提大学时光"}，最多 4 个

## 注意事项
- 只根据信件内容判断，不要凭空编造
- 如果信件数量少（少于 3 封），不要过度推断，只写有把握的
- 各字段如果确实没有足够信息，返回空数组 []

## 输出格式
纯 JSON，不要 markdown，不要解释：
{
  "summary": "这是一个……",
  "latent_place_affinities": [{"name": "..."}],
  "sensory_biases": [{"name": "..."}],
  "identity_signals": [{"name": "..."}],
  "recent_memory_signals": [{"name": "..."}]
}"""


class MemoryService:
    """用户画像构建与上下文加载"""

    async def load_user_context(
        self, db: AsyncSession, user_id: int
    ) -> dict:
        """加载写信所需的用户上下文（近期信件 + 画像）

        Returns:
            {"recent_letters": [str, ...], "profile_summary": str, "profile": dict | None}
        """
        # 查最近 N 封信
        result = await db.execute(
            select(Letter)
            .where(Letter.user_id == user_id)
            .order_by(Letter.timestamp.desc())
            .limit(MAX_RECENT_LETTERS)
        )
        recent = result.scalars().all()
        recent_letters = [
            lt.text[:200] for lt in reversed(recent) if lt.text.strip()
        ]

        # 查画像
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
            "loaded user context: %d recent letters, profile=%s",
            len(recent_letters), "yes" if profile_summary else "no",
        )
        return {
            "recent_letters": recent_letters,
            "profile_summary": profile_summary,
            "profile": profile,
        }

    async def build_profile(
        self, db: AsyncSession, user_id: int, llm
    ) -> None:
        """用最近 5 封信件构建/更新用户画像，写入 PastSelfProfile"""
        result = await db.execute(
            select(Letter)
            .where(Letter.user_id == user_id)
            .order_by(Letter.timestamp.desc())
            .limit(5)
        )
        recent_letters = result.scalars().all()
        recent_letters = list(reversed(recent_letters))  # 按时间正序

        if len(recent_letters) < 3:
            logger.info("profile build skipped: only %d letters", len(recent_letters))
            return

        # 构造 prompt：把每封信截断后拼接
        letter_texts = []
        for i, lt in enumerate(recent_letters, 1):
            snippet = lt.text[:300].replace("\n", " ")
            letter_texts.append(f"第{i}封信（地点：{lt.place or '未知'}，情绪：{lt.mood or '未知'}）：\n{snippet}")

        user_msg = "\n\n".join(letter_texts)
        user_msg += "\n\n请根据以上所有信件，构建用户画像。"

        try:
            raw = llm.chat(
                SYSTEM_PROFILE,
                user_msg,
                temperature=0.4,
                max_tokens=600,
            )
            data = self._parse_json(raw)
        except Exception as e:
            logger.warning("profile LLM call failed: %s", e)
            return

        if not data:
            return

        # 写入 PastSelfProfile（upsert）
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
            profile = PastSelfProfile(
                user_id=user_id,
                summary=data.get("summary", ""),
                latent_place_affinities=data.get("latent_place_affinities", []),
                sensory_biases=data.get("sensory_biases", []),
                identity_signals=data.get("identity_signals", []),
                recent_memory_signals=data.get("recent_memory_signals", []),
                updated_at=now,
            )
            db.add(profile)

        await db.flush()
        logger.info(
            "profile built: summary=%s..., places=%d, sensory=%d",
            data.get("summary", "")[:40],
            len(data.get("latent_place_affinities", [])),
            len(data.get("sensory_biases", [])),
        )

    def _parse_json(self, raw: str) -> dict | None:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("failed to parse profile JSON")
            return None

    def format_context_for_prompt(self, user_context: dict) -> str:
        """将 user_context 格式化为可注入 prompt 的文本"""
        parts = []

        if user_context.get("profile_summary"):
            parts.append(f"用户画像：{user_context['profile_summary']}")

        letters = user_context.get("recent_letters", [])
        if letters:
            parts.append("最近写过的信：")
            for i, lt in enumerate(letters, 1):
                parts.append(f"  {i}. {lt[:150]}")

        return "\n".join(parts) if parts else ""
