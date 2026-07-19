"""诗歌生成服务 — 为明信片作诗

职责：
1. 根据地标和搜索结果生成短诗
2. 生成明信片标题和正文
"""
from __future__ import annotations

from typing import Any

from services.llm_service import LlmService


SYSTEM_POEM = """你是一位细腻的诗人，写温暖、怀旧、克制的短诗。
诗要像明信片上手写的字迹，4-8行。
不要标题，不要解释，只输出诗歌正文。
"""

SYSTEM_TITLE = """为一张故乡明信片取一个标题，10字以内，温暖怀旧。
只输出标题本身，不要引号。"""

SYSTEM_BODY = """以"过去的我"的口吻写一段明信片正文（30-80字）。
温暖、安静、略带怀旧。像是很多年后回看那一天写下的。
只输出正文。"""


class PoemService:
    """诗歌和明信片文案生成"""

    def __init__(self, llm: LlmService | None = None):
        self.llm = llm or LlmService()

    def generate_poem(self, landmark: dict,
                      context: str = "",
                      analysis: dict | None = None) -> str:
        """根据地标和搜索结果生成诗歌"""
        place = landmark.get("name", "故乡")
        desc = landmark.get("description", "")
        msg = f"地点：{place}"
        if desc:
            msg += f"\n描述：{desc}"
        if context:
            msg += f"\n场景：{context[:120]}"
        if analysis:
            tone = analysis.get("emotional_tone", "")
            themes = "、".join(analysis.get("visual_themes", []))
            if tone:
                msg += f"\n情感基调：{tone}"
            if themes:
                msg += f"\n画面元素：{themes}"
        return self.llm.chat(SYSTEM_POEM, msg)

    def generate_title(self, landmark: dict, poem: str,
                       analysis: dict | None = None,
                       user_context: dict | None = None) -> str:
        """生成明信片标题"""
        place = landmark.get("name", "故乡")
        msg = f"地点：{place}\n诗的内容：{poem}"
        if analysis:
            tone = analysis.get("emotional_tone", "")
            if tone:
                msg += f"\n情感：{tone}"
        if user_context:
            summaries = user_context.get("recent_summaries", [])
            if summaries:
                msg += f"\n最近阶段总结：{'；'.join(s['summary_text'][:60] for s in summaries if s.get('summary_text'))}"
        if user_context and user_context.get("profile_summary"):
            msg += f"\n写信人的性格画像：{user_context['profile_summary'][:100]}"
        return self.llm.chat(SYSTEM_TITLE, msg, temperature=0.7, max_tokens=30)

    def generate_body(self, landmark: dict, poem: str,
                      letter_text: str = "",
                      analysis: dict | None = None,
                      user_context: dict | None = None) -> str:
        """生成明信片正文"""
        place = landmark.get("name", "故乡")
        msg = f"地点：{place}\n诗：{poem}"
        if letter_text:
            msg += f"\n来信内容：{letter_text[:150]}"
        if analysis:
            tone = analysis.get("emotional_tone", "")
            if tone:
                msg += f"\n情感基调：{tone}"
        if user_context:
            summaries = user_context.get("recent_summaries", [])
            if summaries:
                msg += f"\n最近阶段总结：{'；'.join(s['summary_text'][:70] for s in summaries if s.get('summary_text'))}"
            memories = user_context.get("recent_memories", [])
            if memories:
                overview = [m.get("memory_overview", "")[:50] for m in memories if m.get("memory_overview")]
                if overview:
                    msg += f"\n最近阶段记忆：{'；'.join(overview)}"
        if user_context and user_context.get("profile_summary"):
            msg += (
                f"\n写信人的性格画像：{user_context['profile_summary'][:120]}\n"
                f"请用符合这个性格的语气来写正文。"
            )
        return self.llm.chat(SYSTEM_BODY, msg, temperature=0.8, max_tokens=150)
