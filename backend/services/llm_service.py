"""DeepSeek LLM 服务。"""
import httpx
from openai import OpenAI

from config import settings

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
