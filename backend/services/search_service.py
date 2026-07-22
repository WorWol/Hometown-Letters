"""Serper 图片搜索服务。"""
import logging

import httpx

from config import settings

logger = logging.getLogger("hometown")


class SearchService:
    """提供文字搜索和图片搜索功能"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.serper_api_key

    async def search_images(self, query: str, num: int = 5) -> list[str]:
        """搜索图片，返回图片 URL 列表"""
        raw = await self._serper_request(settings.serper_image_url, query, num * 2)
        image_urls = []
        for img in raw.get("images", [])[:num]:
            url = img.get("imageUrl")
            if url:
                image_urls.append(url)
        return image_urls

    async def _serper_request(self, url: str, query: str, num: int) -> dict:
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
            logger.warning("[SearchService] 搜索失败: %s: %s", type(e).__name__, str(e)[:80])
            return {}
