"""火山引擎图像生成服务（从 volc_image.py 迁移）

支持两种模式：
1. 使用 volcenginesdkarkruntime SDK（如果已安装）
2. 使用 httpx 直接调用 OpenAI 兼容 API
"""
import base64
import json
import logging
import httpx
from typing import Any

from config import settings

logger = logging.getLogger("hometown")

# 尝试导入 SDK（可选）
try:
    from volcenginesdkarkruntime import Ark as _Ark
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


class ImageService:
    """封装火山方舟图像生成 API"""

    def __init__(self):
        self.client = None

        if _HAS_SDK:
            # SDK 模式也通过 httpx 代理
            proxy = settings.get_proxy_for("volc")
            http_client = None
            if proxy:
                http_client = httpx.Client(proxy=proxy)
            self.client = _Ark(
                base_url=settings.volc_base_url,
                api_key=settings.volc_api_key,
                http_client=http_client,
            )

    # 主模型失败时的备用模型列表
    _FALLBACK_MODELS = [
        "doubao-seedream-4-0-250828",
    ]

    async def generate(self, prompt: str,
                       size: str = "2K",
                       reference_images: list[str] | None = None
                       ) -> dict[str, Any]:
        """生成图像，主模型失败自动切换备用模型"""
        styled_prompt = f"{prompt}. Style: {settings.image_gen_style}"
        if self.client:
            result = await self._generate_sdk(styled_prompt, size, reference_images)
            if result.get("ok"):
                return result
            # SDK 模式也尝试备用模型
            for fb_model in self._FALLBACK_MODELS:
                logger.info("retrying with fallback model: %s", fb_model)
                result = await self._generate_sdk(styled_prompt, size, reference_images, model=fb_model)
                if result.get("ok"):
                    return result
            return result
        return await self._generate_http(styled_prompt, size, reference_images)

    async def _generate_sdk(self, prompt: str, size: str,
                            reference_images: list[str] | None,
                            model: str | None = None) -> dict[str, Any]:
        """使用 SDK 生成（异步）"""
        params: dict[str, Any] = {
            "model": model or settings.volc_model,
            "prompt": prompt,
            "size": size,
            "response_format": "url",
        }
        if reference_images:
            params["image"] = reference_images
        try:
            # SDK 是同步的，在异步中通过 run_in_executor 执行以免阻塞
            import asyncio
            response = await asyncio.to_thread(self.client.images.generate, **params)
            if response.data:
                return {
                    "ok": True,
                    "url": response.data[0].url,
                    "revised_prompt": getattr(response.data[0], "revised_prompt", ""),
                }
            logger.warning("SDK image gen returned no data: %s", response)
            return {"ok": False, "error": str(response)}
        except Exception as e:
            logger.error("SDK image gen exception: %s", e)
            return {"ok": False, "error": str(e)}

    async def _generate_http(self, prompt: str, size: str,
                             reference_images: list[str] | None,
                             model: str | None = None) -> dict[str, Any]:
        """使用 httpx 异步调用 API，失败自动切备用模型"""
        models_to_try = [model] if model else [settings.volc_model] + self._FALLBACK_MODELS
        last_error = ""
        for m in models_to_try:
            result = await self._try_generate_http(prompt, size, reference_images, m)
            if result.get("ok"):
                return result
            last_error = result.get("error", "")
            logger.warning("image gen model=%s failed: %s, trying next...", m, last_error[:80])
        return {"ok": False, "error": last_error or "all models failed"}

    async def _try_generate_http(self, prompt: str, size: str,
                                 reference_images: list[str] | None,
                                 model: str) -> dict[str, Any]:
        """单次 HTTP 生图调用"""
        url = f"{settings.volc_base_url.rstrip('/')}/images/generations"
        headers = {
            "Authorization": f"Bearer {settings.volc_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "size": self._normalize_size(size),
            "n": 1,
            "response_format": "url",
        }
        if reference_images:
            payload["image"] = reference_images

        try:
            proxy = settings.get_proxy_for("volc")
            async with httpx.AsyncClient(proxy=proxy,
                                         timeout=settings.image_gen_timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("data", [])
                if choices:
                    return {
                        "ok": True,
                        "url": choices[0].get("url", ""),
                        "revised_prompt": choices[0].get("revised_prompt", ""),
                    }
                logger.warning("HTTP image gen returned no data: %s", json.dumps(data, ensure_ascii=False)[:500])
                return {"ok": False, "error": json.dumps(data, ensure_ascii=False)[:500]}
        except Exception as e:
            logger.error("HTTP image gen exception: %s", e)
            return {"ok": False, "error": str(e)}

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
    async def download_image_bytes(url: str) -> bytes | None:
        """下载网络图片并返回原始字节（用于本地缓存）"""
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }
        proxy = settings.get_proxy_for("serper")
        try:
            async with httpx.AsyncClient(proxy=proxy,
                                         timeout=settings.download_timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None

    @staticmethod
    async def download_and_encode(url: str) -> str | None:
        """下载网络图片并转为 base64 data URL（用于参考图）"""
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }
        proxy = settings.get_proxy_for("serper")  # 搜图 URL 也在墙外，走同样的代理
        try:
            async with httpx.AsyncClient(proxy=proxy,
                                         timeout=settings.download_timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                img_data = base64.b64encode(resp.content).decode()
                ext = url.rsplit(".", 1)[-1].lower() if "." in url else "jpeg"
                mime = "jpeg" if ext in ("jpg", "jpeg") else "png"
                return f"data:image/{mime};base64,{img_data}"
        except Exception:
            return None
