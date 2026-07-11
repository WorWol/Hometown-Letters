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
                      context: str = "") -> str:
        """根据地标和搜索结果生成诗歌"""
        place = landmark.get("name", "故乡")
        desc = landmark.get("description", "")
        msg = f"地点：{place}"
        if desc:
            msg += f"\n描述：{desc}"
        if context:
            msg += f"\n场景：{context[:120]}"
        return self.llm.chat(SYSTEM_POEM, msg)

    def generate_title(self, landmark: dict, poem: str) -> str:
        """生成明信片标题"""
        place = landmark.get("name", "故乡")
        msg = f"地点：{place}\n诗的内容：{poem}"
        return self.llm.chat(SYSTEM_TITLE, msg, temperature=0.7, max_tokens=30)

    def generate_body(self, landmark: dict, poem: str,
                      letter_text: str = "") -> str:
        """生成明信片正文"""
        place = landmark.get("name", "故乡")
        msg = f"地点：{place}\n诗：{poem}"
        if letter_text:
            msg += f"\n来信提及：{letter_text[:100]}"
        return self.llm.chat(SYSTEM_BODY, msg, temperature=0.8, max_tokens=150)

    def generate_image_prompt(self, landmark: dict,
                              scene_context: str = "") -> str:
        """生成英文图像提示词（全像素风，去掉 painterly 矛盾方向）"""
        place = landmark.get("name", "故乡")
        desc = landmark.get("description", "")
        scene_type = landmark.get("scene_type", "other")

        style_map = {
            "lakeside_dam": "waterside scene, gentle lake breeze, warm afternoon light",
            "bridge_roadside": "old stone bridge, soft wind, dappled sunlight through trees",
            "school_gate": "afternoon school gate, nostalgic warm golden light",
            "street_food": "lively street, warm lantern light, steam rising from food stalls",
            "path_to_pond": "shaded path, cool water reflections, dappled light, quiet mood",
            "park": "peaceful park, morning light, people exercising under trees, birds",
            "market": "busy market, colorful stalls, morning sunlight through awnings",
            "temple": "ancient temple, incense smoke curling, quiet sunlit courtyard",
        }
        style = style_map.get(scene_type, "peaceful hometown scene, warm nostalgic atmosphere")

        msg = (
            f"Scene: {place}\n"
            f"Description: {desc}\n"
            f"Style/atmosphere: {style}\n"
            f"Extra: {scene_context[:80] if scene_context else 'A warm summer day'}\n\n"
            f"Write a detailed English image generation prompt (50-80 words) for "
            f"a RETRO 16-BIT PIXEL ART scene. Key requirements:\n"
            f"- Must be pixel art with visible pixel grid and crisp blocky edges\n"
            f"- Flat 2D shading, limited color palette, warm nostalgic colors\n"
            f"- SNES/GBA-era game screenshot aesthetic\n"
            f"- NO photorealism, NO smooth gradients, NO 3D rendering, NO painterly brush strokes\n"
            f"- Include specific visual details: lighting, atmosphere, composition"
        )

        return self.llm.chat(
            "You are an expert at writing pixel art image generation prompts. "
            "Output only the English prompt, no explanations, no markdown.",
            msg,
            temperature=0.7,
            max_tokens=200,
        )
