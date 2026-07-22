"""诗歌生成服务 - 为明信片作诗

职责：
1. 根据地点和搜索结果生成短诗
2. 生成明信片标题和正文
"""
from __future__ import annotations


from services.llm_service import LlmService
from services.prompt_service import get_prompt

class PoemService:
    """诗歌和明信片文案生成"""

    def __init__(self, llm: LlmService | None = None):
        self.llm = llm or LlmService()

    def generate_poem(self, place_context: dict,
                      context: str = "",
                      analysis: dict | None = None) -> str:
        """根据地点和搜索结果生成诗歌"""
        place = place_context.get("name", "故乡")
        desc = place_context.get("description", "")
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
        return self.llm.chat(get_prompt("poem"), msg)

    def generate_title(self, place_context: dict, poem: str,
                       analysis: dict | None = None,
                       user_context: dict | None = None) -> str:
        """生成明信片标题"""
        place = place_context.get("name", "故乡")
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
        return self.llm.chat(get_prompt("title"), msg, temperature=0.7, max_tokens=30)

    def generate_body(self, place_context: dict, poem: str,
                      letter_text: str = "",
                      analysis: dict | None = None,
                      user_context: dict | None = None) -> str:
        """生成明信片正文"""
        place = place_context.get("name", "故乡")
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
        return self.llm.chat(get_prompt("body"), msg, temperature=0.8, max_tokens=150)
