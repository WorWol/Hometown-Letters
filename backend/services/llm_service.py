"""LLM 服务 - 火山豆包多模态模型，提供聊天、agent 工具调用和视觉描述。

主脑模型 doubao-seed-2-0-lite-260428 支持多模态（文本+图片输入）和 function calling，
既能做 agent 分析（调 search_web 查证），又能看图（描述角色形象等）。
"""
import json
import asyncio
import httpx
from openai import OpenAI, AsyncOpenAI

from config import settings


class LlmService:
    """封装火山方舟豆包 LLM（多模态，支持 function calling + 图片输入）。"""

    def __init__(self, api_key: str | None = None):
        api_key = api_key or settings.volc_api_key
        proxy = settings.get_proxy_for("volc")
        # 始终 trust_env=False：不走 macOS 系统代理，直连火山 API（系统代理可能连不上）
        client_kwargs: dict = {"timeout": settings.llm_timeout, "trust_env": False}
        if proxy:
            client_kwargs["proxy"] = proxy
        self.client = OpenAI(
            api_key=api_key,
            base_url=settings.volc_base_url,
            http_client=httpx.Client(**client_kwargs),
        )
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.volc_base_url,
            http_client=httpx.AsyncClient(**client_kwargs),
        )
        self.model = settings.volc_llm_model

    def chat(self, system_prompt: str, user_message: str,
             model: str | None = None,
             temperature: float = 0.8,
             max_tokens: int = 500) -> str:
        """基础聊天方法（无工具）。"""
        resp = self.client.chat.completions.create(
            model=model or self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    async def chat_with_tools(self, system_prompt: str, user_message: str,
                              tools: list[dict], tool_handler,
                              model: str | None = None,
                              temperature: float = 0.4,
                              max_tokens: int = 1500,
                              max_rounds: int = 5) -> str:
        """agent 聊天：模型可调工具，循环直到无 tool_calls 或达到 max_rounds。

        tool_handler: async 回调 (name, args) -> str/可 str 化的结果。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        last_content = ""
        for _ in range(max_rounds):
            resp = await self.async_client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            msg = resp.choices[0].message
            last_content = (msg.content or "").strip()
            if not msg.tool_calls:
                return last_content
            # 把含 tool_calls 的 assistant 消息加入对话
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
            # 并行执行本轮所有工具调用（asyncio.gather 保序）
            async def _run_tool(tc):
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    result = await tool_handler(tc.function.name, args)
                except Exception as e:
                    result = f"工具调用失败: {e}"
                return {"tool_call_id": tc.id, "content": str(result)}
            tool_results = await asyncio.gather(*(_run_tool(tc) for tc in msg.tool_calls))
            for tr in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_call_id"],
                    "content": tr["content"],
                })
        return last_content

    async def vision_describe(self, image_data_url: str, prompt: str) -> str:
        """看图描述（多模态）。image_data_url 为 data:image/...;base64,... 格式。

        用于让主脑看参考图并描述内容（如角色形象特征），输出纯文本。
        """
        resp = await self.async_client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
            temperature=0.3,
            max_tokens=220,
        )
        return resp.choices[0].message.content.strip()
