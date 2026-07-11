"""Serper API 搜索服务（从 demo.py 迁移）"""
import os
import re
import httpx
from typing import Any

from config import settings


class SearchService:
    """提供文字搜索和图片搜索功能"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.serper_api_key

    async def search_text(self, query: str, num: int = 10) -> list[dict[str, Any]]:
        """搜索文字信息并提取结构化的结果"""
        raw = await self._serper_request(settings.serper_search_url, query, num)
        return self._extract_text_details(raw)

    async def search_images(self, query: str, num: int = 5) -> list[str]:
        """搜索图片，返回图片 URL 列表"""
        raw = await self._serper_request(settings.serper_image_url, query, num * 2)
        image_urls = []
        for img in raw.get("images", [])[:num]:
            url = img.get("imageUrl")
            if url:
                image_urls.append(url)
        return image_urls

    async def _serper_request(self, url: str, query: str, num: int) -> dict[str, Any]:
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": num}
        proxy = settings.get_proxy_for("serper")
        try:
            async with httpx.AsyncClient(proxy=proxy,
                                         timeout=settings.search_timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException,
                httpx.RemoteProtocolError, httpx.HTTPStatusError) as e:
            print(f"[SearchService] 搜索失败: {type(e).__name__}: {str(e)[:80]}")
            return {}

    def _extract_text_details(self, data: dict) -> list[dict[str, Any]]:
        results = []
        kg = data.get("knowledgeGraph")
        if kg:
            desc = kg.get("description", "")
            if desc:
                results.append({
                    "type": "知识图谱",
                    "title": kg.get("title", "知识图谱"),
                    "content": desc,
                    "link": kg.get("website", ""),
                })
        answer = data.get("answerBox")
        if answer:
            ans_text = answer.get("answer", "") or answer.get("snippet", "")
            if ans_text:
                results.append({
                    "type": "答案框",
                    "title": answer.get("title", "直接回答"),
                    "content": ans_text,
                    "link": "",
                })
        for item in data.get("organic", [])[:10]:
            title = item.get("title", "无标题")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            if snippet:
                results.append({
                    "type": "网页摘要",
                    "title": title,
                    "content": snippet,
                    "link": link,
                })
        return results
