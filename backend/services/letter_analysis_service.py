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

logger = logging.getLogger(__name__)

SYSTEM_ANALYSIS = """你是一位情感细腻的故乡叙事者，善于从只言片语中捕捉画面。

用户写了一封信，信中可能提到了某个地点。请深度分析这封信，提取以下信息：

## 你的任务
1. **visual_themes**：信中提到或隐含的具体视觉元素（建筑、自然景物、光线、颜色、季节、人物活动等），3-8 个，用中文
2. **emotional_tone**：情感基调，如"怀念/温暖/略带感伤"、"兴奋/青春/活力"，用中文短语
3. **scene_type**：最匹配的场景类型，从以下选一个: lakeside_dam, bridge_roadside, school_gate, street_food, path_to_pond, park, market, temple, mountain, city, other
4. **search_keywords**：用于图片搜索的关键词列表（3-5 个），必须包含具体的地理位置上下文。
   - 如果你知道信中地点所在的城市，一定要加上城市名
   - 中文+英文混用，覆盖面更广
   - 例如：如果信中提到"华中科技大学"，你应该写 "武汉 华中科技大学 梧桐 校园"
5. **core_place**：信件中最核心的地点名称。如果用户明确写出了地名就用它；如果信中没提但给了 place_hint 就用 place_hint；如果都没有则用家乡名称
6. **generation_place**：本次 Web Search 和图片生成实际使用的地点。明确地点时用信件地点；没有明确地点时用家乡地址，并补充一个当地代表性景点或生活场景。
7. **image_prompt**：根据前面对信件场景和情感的分析，写一段英文图像生成提示词（50-80词）。必须是 RETRO 16-BIT PIXEL ART 风格。
   关键要求：
   - 必须描述具体、可辨识的建筑特征（如红砖教学楼、梧桐树下的石阶、图书馆的拱形窗户）——不能只是泛泛的"校园林荫道"
   - 视角必须是人的平视/仰视角度，能看到建筑正面或侧面的亲切视角，严禁俯视、鸟瞰、远景
   - 只描述视觉元素、光线、氛围、色彩，不要出现具体地名

   好例子："16-bit pixel art of red brick campus buildings with ivy-covered walls seen from ground level, parasol trees framing the view, students sitting on stone steps in golden hour light, warm autumn colors, nostalgic game screenshot aesthetic"

   坏例子（太泛，没特征）："16-bit pixel art of a tree-lined campus avenue at golden hour, students walking"

## 用户画像与历史
如果提供了用户画像和最近写过的信，请注意：
- 如果当前信件和过去的信提到了同一地点或相关场景，保持视觉主题和情感基调的连贯性
- 如果用户画像显示了某种性格特质（如"念旧""安静"），分析时尊重这种特质
- 画像信息仅供参考，不要强行套用——始终以当前信件内容为主

## 注意事项
- 即使用户设的故乡城市和信中提到的地方不同（如故乡是郴州但信提到武汉的大学），你必须以信件中提到的地方为准
- 如果信中只是日常问候而没有具体地点，就根据情感基调推断一个场景
- 搜索关键词中必须包含正确的地理位置
- image_prompt 必须是可直接使用的英文，50-80词，像素风

## 输出格式
纯 JSON，不要 markdown，不要解释：

{
  "visual_themes": ["梧桐树", "教学楼", "黄昏", "学生们"],
  "emotional_tone": "怀念/温暖/略带感伤",
  "scene_type": "school_gate",
  "search_keywords": [
    "武汉 华中科技大学 梧桐 校园",
    "university campus tree-lined path autumn",
    "华中科技大学 教学楼 夕阳"
  ],
    "core_place": "华中科技大学",
    "generation_place": "武汉华中科技大学",
  "image_prompt": "16-bit pixel art of red brick campus buildings with ivy-covered walls seen from ground level, parasol trees framing the view, students sitting on stone steps in golden hour light, warm autumn colors, nostalgic SNES-era game screenshot aesthetic"
}
"""


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
                SYSTEM_ANALYSIS,
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
