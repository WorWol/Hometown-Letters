"""文件系统图片存储 — 替代内存缓存"""
from __future__ import annotations

import os
from pathlib import Path

import aiofiles

from config import settings

IMAGES_DIR = Path(__file__).resolve().parent.parent / "generated_images"
IMAGES_DIR.mkdir(exist_ok=True)


async def save_image(image_id: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """保存图片到文件系统，返回相对路径"""
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    ext = ext_map.get(content_type, ".jpg")
    filename = f"{image_id}{ext}"
    filepath = IMAGES_DIR / filename
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(data)
    return filename


def get_image_path(image_id: str) -> Path | None:
    """根据 image_id 查找已存在的图片文件"""
    for ext in (".jpg", ".png", ".webp"):
        p = IMAGES_DIR / f"{image_id}{ext}"
        if p.is_file():
            return p
    return None


async def read_image(image_id: str) -> tuple[bytes, str] | None:
    """读取图片，返回 (bytes, content_type)"""
    ext_map = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    for ext in (".jpg", ".png", ".webp"):
        p = IMAGES_DIR / f"{image_id}{ext}"
        if p.is_file():
            async with aiofiles.open(p, "rb") as f:
                data = await f.read()
            return data, ext_map.get(ext, "image/jpeg")
    return None


def get_image_url(image_id: str) -> str:
    """生成图片的 HTTP URL（v2 API）"""
    return f"http://127.0.0.1:8787/api/v2/image/{image_id}"
