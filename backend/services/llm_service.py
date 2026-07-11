"""DeepSeek LLM 服务 — 用于生成诗歌、分析信件、构建明信片文案"""
import json
import os
from typing import Any
import httpx
from openai import OpenAI

from config import settings

SYSTEM_PROMPTS = {
    "poem": "你是一位细腻的诗人。根据用户描述的地点，创作一首短诗（4-8行）。"
            "诗要温暖、怀旧，像从远方寄来的明信片上的字迹。"
            "只输出诗歌正文，不要解释，不要标题。",

    "letter_analysis": "你是一位理解故乡情感的阅读者。分析用户的信件，提取关键信息。"
                       "以 JSON 格式返回："
                       '{"place": "提到的地方名（如无则为空）",'
                       '"mood": "情绪关键词",'
                       '"keywords": ["关键词列表"]}',

    "postcard_title": "根据以下素材，生成一个明信片标题（10字以内，温暖怀旧风格）。只输出标题本身。",

    "postcard_body": "根据以下素材，以\"过去的我\"的口吻写一段明信片正文（30-80字）。"
                     "温暖、安静、略带怀旧。像写给未来的自己。只输出正文。",

    "image_prompt": "将以下场景描述转化为英文图像生成提示词（50词以内），"
                    "适用于 AI 绘画。强调光影和氛围。只输出英文 prompt。",
}


class LlmService:
    """封装 DeepSeek/OpenAI 兼容的 LLM 调用"""

    def __init__(self, api_key: str | None = None):
        api_key = api_key or settings.deepseek_api_key
        # 为 OpenAI SDK 配置代理
        proxy = settings.get_proxy_for("deepseek")
        http_client = None
        if proxy:
            http_client = httpx.Client(proxy=proxy, timeout=settings.llm_timeout)
        self.client = OpenAI(
            api_key=api_key,
            base_url=settings.deepseek_base_url,
            http_client=http_client,
        )

    def chat(self, system_prompt: str, user_message: str,
             model: str = "deepseek-chat",
             temperature: float = 0.8,
             max_tokens: int = 500) -> str:
        """基础聊天方法"""
        resp = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    def generate_poem(self, place: str, context: str = "") -> str:
        """根据地点生成一首诗"""
        msg = f"地点：{place}\n背景：{context}\n请为此地写一首明信片上的短诗。"
        return self.chat(SYSTEM_PROMPTS["poem"], msg)

    def analyze_letter(self, letter_text: str) -> dict[str, Any]:
        """分析信件，提取地点和情绪"""
        try:
            result = self.chat(SYSTEM_PROMPTS["letter_analysis"],
                               letter_text, temperature=0.3)
            # 尝试解析 JSON
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                clean = clean.rsplit("\n", 1)[0]
                if clean.endswith("```"):
                    clean = clean[:-3]
            return json.loads(clean)
        except (json.JSONDecodeError, Exception):
            return {"place": "", "mood": "平静", "keywords": []}

    def generate_postcard_title(self, place: str, poem: str,
                                context: str = "") -> str:
        """生成明信片标题"""
        msg = f"地点：{place}\n诗：{poem}\n背景：{context}"
        return self.chat(SYSTEM_PROMPTS["postcard_title"], msg)

    def generate_postcard_body(self, place: str, poem: str,
                               context: str = "") -> str:
        """生成明信片正文"""
        msg = f"地点：{place}\n诗：{poem}\n背景：{context}"
        return self.chat(SYSTEM_PROMPTS["postcard_body"], msg)

    def generate_image_prompt(self, place: str, scene_desc: str = "") -> str:
        """生成英文图像提示词"""
        msg = f"地点：{place}\n场景描述：{scene_desc}"
        return self.chat(SYSTEM_PROMPTS["image_prompt"], msg,
                         temperature=0.7, max_tokens=200)
