"""火山引擎图像生成服务。"""
import base64
import httpx
from typing import Any

from config import settings


class ImageService:
    """封装火山方舟图像生成 API"""

    async def generate(self, prompt: str,
                       size: str = "2K",
                       reference_images: list[str] | None = None
                       ) -> dict[str, Any]:
        """使用配置的单一模型生成图像；失败直接返回失败。"""
        styled_prompt = f"{prompt}. Style: {settings.image_gen_style}"
        url = f"{settings.volc_base_url.rstrip('/')}/images/generations"
        payload = {
            "model": settings.volc_model,
            "prompt": styled_prompt,
            "size": self._normalize_size(size),
            "n": 1,
            "response_format": "url",
        }
        if reference_images:
            payload["image"] = reference_images
        headers = {
            "Authorization": f"Bearer {settings.volc_api_key}",
            "Content-Type": "application/json",
        }
        proxy = settings.get_proxy_for("volc")
        async with httpx.AsyncClient(proxy=proxy, timeout=settings.image_gen_timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            choices = resp.json().get("data", [])
        if not choices or not choices[0].get("url"):
            raise ValueError("image generation returned no image URL")
        return {
            "ok": True,
            "url": choices[0]["url"],
            "revised_prompt": choices[0].get("revised_prompt", ""),
        }

    @staticmethod
    def _normalize_size(size: str) -> str:
        """标准化尺寸格式"""
        # 注意：火山引擎要求图片像素数 >= 3,686,400
        mapping = {
            "2K": "2048x2048",      # 4,194,304 px ✓
            "HD": "1920x1920",      # 3,686,400 px ✓ (刚好达标)
            "1K": "1024x1024",      # 1,048,576 px ✗ (不达标，保留不变)
        }
        return mapping.get(size.upper(), size)

    @staticmethod
    async def download_image_bytes(url: str) -> bytes:
        """下载图片；失败直接抛出异常。"""
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }
        proxy = settings.get_proxy_for("volc")
        async with httpx.AsyncClient(proxy=proxy, timeout=settings.download_timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content

    @staticmethod
    async def download_and_encode(url: str) -> str:
        """下载网络图片并转为 base64 data URL；失败直接抛出异常。"""
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }
        proxy = settings.get_proxy_for("serper")
        async with httpx.AsyncClient(proxy=proxy, timeout=settings.download_timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            img_data = base64.b64encode(resp.content).decode()
            ext = url.rsplit(".", 1)[-1].lower() if "." in url else "jpeg"
            mime = "jpeg" if ext in ("jpg", "jpeg") else "png"
            return f"data:image/{mime};base64,{img_data}"
