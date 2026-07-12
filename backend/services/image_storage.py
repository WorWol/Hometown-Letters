"""图片存储 — 本地文件系统 / 阿里云 OSS 双后端

自动检测：设置了 OSS_ACCESS_KEY_ID 则走 OSS，否则走本地文件系统。
"""
from __future__ import annotations

import os
from pathlib import Path

import aiofiles

# ── 本地存储目录 ──
IMAGES_DIR = Path(__file__).resolve().parent.parent / "generated_images"
IMAGES_DIR.mkdir(exist_ok=True)

# ── OSS 配置（延迟加载，避免本地开发时缺少依赖报错）──
_oss_bucket = None
_oss_checked = False


def _use_oss() -> bool:
    return bool(
        os.environ.get("OSS_ACCESS_KEY_ID")
        and os.environ.get("OSS_ACCESS_KEY_SECRET")
        and os.environ.get("OSS_ENDPOINT")
        and os.environ.get("OSS_BUCKET_NAME")
    )


def _get_bucket():
    """延迟初始化 OSS Bucket，只在首次调用时连接"""
    global _oss_bucket, _oss_checked
    if not _oss_checked:
        _oss_checked = True
        if _use_oss():
            import oss2
            auth = oss2.Auth(
                os.environ["OSS_ACCESS_KEY_ID"],
                os.environ["OSS_ACCESS_KEY_SECRET"],
            )
            _oss_bucket = oss2.Bucket(
                auth,
                os.environ["OSS_ENDPOINT"],
                os.environ["OSS_BUCKET_NAME"],
            )
    return _oss_bucket


# ── 公共 API ──

async def save_image(image_id: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """保存图片，返回存储 key（文件名）"""
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    ext = ext_map.get(content_type, ".jpg")
    key = f"{image_id}{ext}"

    bucket = _get_bucket()
    if bucket:
        # OSS 模式：上传
        bucket.put_object(key, data, headers={"Content-Type": content_type})
    else:
        # 本地模式：写文件
        filepath = IMAGES_DIR / key
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(data)

    return key


async def read_image(image_id: str) -> tuple[bytes, str] | None:
    """读取图片，返回 (bytes, content_type)"""
    ext_map = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

    bucket = _get_bucket()
    if bucket:
        # OSS 模式
        for ext in (".jpg", ".png", ".webp"):
            key = f"{image_id}{ext}"
            try:
                result = bucket.get_object(key)
                return result.read(), ext_map.get(ext, "image/jpeg")
            except Exception:
                continue
        return None
    else:
        # 本地模式
        for ext in (".jpg", ".png", ".webp"):
            p = IMAGES_DIR / f"{image_id}{ext}"
            if p.is_file():
                async with aiofiles.open(p, "rb") as f:
                    data = await f.read()
                return data, ext_map.get(ext, "image/jpeg")
        return None


def get_image_url(image_id: str, api_prefix: str = "/api/image") -> str:
    """生成图片的 HTTP URL

    OSS 模式：直接返回 OSS 公网 URL（或 CDN 域名）
    本地模式：返回后端代理路由
    """
    bucket = _get_bucket()
    if bucket:
        cdn = os.environ.get("OSS_CDN_DOMAIN", "")
        endpoint = os.environ.get("OSS_ENDPOINT", "")
        bucket_name = os.environ.get("OSS_BUCKET_NAME", "")

        # 找实际存在的扩展名
        ext = ".jpg"
        for e in (".jpg", ".png", ".webp"):
            key = f"{image_id}{e}"
            try:
                bucket.head_object(key)
                ext = e
                break
            except Exception:
                continue

        key = f"{image_id}{ext}"
        if cdn:
            return f"https://{cdn}/{key}"
        return f"https://{bucket_name}.{endpoint}/{key}"

    return f"{api_prefix}/{image_id}"
