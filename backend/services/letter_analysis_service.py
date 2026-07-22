"""信件深度分析服务 — 解析信件的场景/情感/视觉元素

职责：
1. 提取用户信件中的视觉主题和情感基调
2. 生成智能图片搜索关键词（自动补充地理上下文）
3. 识别核心地点（用于地标匹配）

这是整个信件驱动管道的入口，所有下游（搜索/筛选/提示词）
都依赖这里的分析结果。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from services.llm_service import LlmService
from services.prompt_service import get_prompt

logger = logging.getLogger(__name__)



class LetterAnalysisService:
    """信件分析 — 驱动整个图片管道的入口"""

    def __init__(self, llm: LlmService | None = None):
        self.llm = llm or LlmService()

    def analyze_letter_deep(
        self,
        letter_text: str,
        place_hint: str = "",
        mood_hint: str = "",
        hometown: dict | None = None,
        user_context: dict | None = None,
        style_hint: str | None = None,
    ) -> dict[str, Any]:
        """深度分析信件，返回结构化结果"""
        if not letter_text.strip() and not place_hint.strip() and not hometown:
            return self._empty_result()

        # 构建用户消息
        msg_parts = []
        if letter_text.strip():
            msg_parts.append(f"信件内容：\n{letter_text}")
        if place_hint.strip():
            msg_parts.append(f"地点提示：{place_hint}")
        if mood_hint.strip():
            msg_parts.append(f"情绪提示：{mood_hint}")
        if hometown:
            hometown_label = self._hometown_label(hometown)
            if hometown_label:
                msg_parts.append(
                    f"用户保存的故乡地址是：{hometown_label}。"
                    "如果信件没有明确地点，必须使用这个故乡地址作为图片搜索后备地点，"
                    "并补充一个当地代表性景点或生活场景；如果信件明确提到了其他地点，必须以信件地点为准。"
                )

        # 注入用户画像和历史信件上下文
        if user_context:
            ctx_text = self._format_user_context(user_context)
            if ctx_text:
                msg_parts.append(ctx_text)

        user_msg = "\n\n".join(msg_parts)

        try:
            raw = self.llm.chat(
                get_prompt("letter_analysis", style_hint=style_hint),
                user_msg,
                temperature=0.4,
                max_tokens=600,
            )
            result = self._parse_json(raw)

            # 补充默认值
            result.setdefault("visual_themes", [])
            result.setdefault("emotional_tone", mood_hint or "温暖/怀念")
            result.setdefault("scene_type", "other")
            result.setdefault("search_keywords", [])
            hometown_label = self._hometown_label(hometown or {})
            result.setdefault("core_place", place_hint or hometown_label)
            result.setdefault("generation_place", result.get("core_place") or hometown_label)
            result["core_place"] = result.get("core_place") or place_hint or hometown_label
            result["generation_place"] = result.get("generation_place") or result["core_place"]
            if not result["search_keywords"] and result["generation_place"]:
                result["search_keywords"] = [
                    f"{result['generation_place']} 风景 生活场景",
                    f"{result['generation_place']} scenery",
                ]
            result.setdefault("image_prompt", self._build_image_prompt(result))

            logger.info(
                "letter analysis: core_place=%s, tone=%s, themes=%s",
                result["core_place"], result["emotional_tone"], result["visual_themes"],
            )
            return result

        except Exception as e:
            logger.warning("letter analysis failed: %s, using fallback", e)
            return self._fallback(letter_text, place_hint, mood_hint, hometown)

    @staticmethod
    def _hometown_label(hometown: dict) -> str:
        return "".join(
            str(hometown.get(key, "")).strip()
            for key in ("province", "city", "county")
            if str(hometown.get(key, "")).strip()
        )

    @staticmethod
    def _format_user_context(user_context: dict) -> str:
        """将 user_context 格式化为注入 prompt 的文本"""
        from services.memory_service import MemoryService
        return MemoryService().format_context_for_prompt(user_context)

    def _parse_json(self, raw: str) -> dict[str, Any]:
        clean = raw.strip()
        if clean.startswith("```"):
            # 去掉 markdown 代码块标记
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
        return json.loads(clean)

    def _empty_result(self) -> dict[str, Any]:
        return {
            "visual_themes": [],
            "emotional_tone": "温暖/怀念",
            "scene_type": "other",
            "search_keywords": [],
            "core_place": "",
            "generation_place": "",
            "image_prompt": (
                "16-bit pixel art of a peaceful hometown scene, warm golden light, "
                "nostalgic atmosphere, quiet streets or paths, soft shadows, "
                "SNES-era game screenshot aesthetic"
            ),
        }

    def _fallback(
        self, letter_text: str, place_hint: str, mood_hint: str,
        hometown: dict | None = None,
    ) -> dict[str, Any]:
        """LLM 调用失败时的降级方案"""
        core_place = place_hint or self._hometown_label(hometown or {})
        search_kws = []
        if core_place:
            search_kws = [f"{core_place} 风景 生活场景", f"{core_place} scenery"]
        return {
            "visual_themes": [],
            "emotional_tone": mood_hint or "温暖/怀念",
            "scene_type": "other",
            "search_keywords": search_kws,
            "core_place": core_place,
            "generation_place": core_place,
            "image_prompt": (
                "16-bit pixel art of a warm nostalgic hometown scene, "
                "soft golden light, peaceful atmosphere, quiet charm, "
                "SNES-era game screenshot aesthetic"
            ),
        }

    def _build_image_prompt(self, analysis: dict) -> str:
        """当 LLM 没返回 image_prompt 时，用 visual_themes + scene_type 拼接"""
        themes_cn = "、".join(analysis.get("visual_themes", []))
        tone = analysis.get("emotional_tone", "")
        scene_type = analysis.get("scene_type", "other")
        scene_map = {
            "school_gate": "a quiet campus scene",
            "lakeside_dam": "a peaceful waterside scene",
            "bridge_roadside": "an old bridge with dappled sunlight",
            "street_food": "a lively street with warm lantern glow",
            "path_to_pond": "a shaded path leading to water",
            "park": "a peaceful park under soft morning light",
            "market": "a colorful market with morning light",
            "temple": "a quiet temple courtyard with incense",
            "mountain": "a misty mountain landscape",
            "city": "a nostalgic city street scene",
            "other": "a warm hometown scene",
        }
        scene = scene_map.get(scene_type, "a warm nostalgic scene")
        return (
            f"16-bit pixel art of {scene}, "
            f"visual elements: {themes_cn}, "
            f"{tone} atmosphere, warm nostalgic lighting, "
            "SNES-era game screenshot aesthetic"
        )
