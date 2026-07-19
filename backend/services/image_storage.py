"""图片存储：本地开发目录或私有 OSS，统一保存 WebP 变体。"""
from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

import aiofiles
from PIL import Image

from config import settings

IMAGES_DIR = Path(__file__).resolve().parent.parent / "generated_images"
IMAGES_DIR.mkdir(exist_ok=True)
_oss_buckets: dict[str, object] = {}


def _use_oss() -> bool:
    return settings.storage_backend.lower() == "oss"


def validate_storage_config() -> None:
    """在应用启动时校验图片存储配置，不让错误延迟到首次生成。"""
    backend = settings.storage_backend.lower()
    if backend not in {"local", "oss"}:
        raise RuntimeError(f"STORAGE_BACKEND must be local or oss, got: {settings.storage_backend}")
    if backend == "oss":
        missing = [
            name
            for name, value in {
                "OSS_ACCESS_KEY_ID": settings.oss_access_key_id,
                "OSS_ACCESS_KEY_SECRET": settings.oss_access_key_secret,
                "OSS_UPLOAD_ENDPOINT": settings.oss_upload_endpoint,
                "OSS_PUBLIC_ENDPOINT": settings.oss_public_endpoint,
                "OSS_BUCKET_NAME": settings.oss_bucket_name,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "OSS storage is enabled but required configuration is missing: "
                + ", ".join(missing)
            )


def _get_bucket(kind: str):
    if not _use_oss():
        return None
    if kind not in {"upload", "public"}:
        raise ValueError(f"unknown OSS bucket kind: {kind}")
    validate_storage_config()
    if kind not in _oss_buckets:
        import oss2

        endpoint = (
            settings.oss_upload_endpoint
            if kind == "upload"
            else settings.oss_public_endpoint
        )
        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        _oss_buckets[kind] = oss2.Bucket(auth, endpoint, settings.oss_bucket_name)
    return _oss_buckets[kind]


def _encode_variant(source: Image.Image, max_size: int, quality: int) -> bytes:
    image = source.copy()
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    output = BytesIO()
    image.save(output, format="WEBP", quality=quality, method=6)
    return output.getvalue()


def image_variant_keys(user_id: int, image_id: str) -> dict[str, str]:
    """生成一次明信片对应的三个 object key。"""
    prefix = settings.oss_object_prefix.strip("/") or "postcards"
    return {
        name: f"{prefix}/{user_id}/{image_id}/{name}.webp"
        for name in ("thumb", "card", "original")
    }


async def save_image_variants(user_id: int, image_id: str, data: bytes) -> dict[str, str]:
    """保存 thumb/card/original 三种图片，返回 object key。"""
    with Image.open(BytesIO(data)) as source:
        variants = {
            "thumb": _encode_variant(source, 480, 78),
            "card": _encode_variant(source, 1200, 86),
            "original": _encode_variant(source, 2048, 90),
        }

    keys = image_variant_keys(user_id, image_id)
    bucket = _get_bucket("upload")
    uploaded_keys: list[str] = []
    try:
        for name, payload in variants.items():
            key = keys[name]
            if bucket:
                result = await asyncio.to_thread(
                    bucket.put_object,
                    key,
                    payload,
                    headers={
                        "Content-Type": "image/webp",
                        "Cache-Control": "private, max-age=31536000, immutable",
                    },
                )
                if not 200 <= result.status < 300:
                    raise RuntimeError(f"OSS upload failed for {key}: HTTP {result.status}")
            else:
                path = IMAGES_DIR / key
                path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(path, "wb") as file:
                    await file.write(payload)
            uploaded_keys.append(key)
    except Exception:
        if bucket:
            await asyncio.gather(
                *(asyncio.to_thread(bucket.delete_object, key) for key in uploaded_keys),
                return_exceptions=True,
            )
        else:
            for key in uploaded_keys:
                (IMAGES_DIR / key).unlink(missing_ok=True)
        raise
    return keys


async def delete_image_variants(keys: dict[str, str]) -> None:
    """删除一次生成已经写入的全部图片，供数据库保存失败时回滚对象。"""
    object_keys = [key for key in keys.values() if key]
    if not object_keys:
        return
    bucket = _get_bucket("upload")
    if bucket:
        results = await asyncio.gather(
            *(asyncio.to_thread(bucket.delete_object, key) for key in object_keys),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            raise RuntimeError(f"failed to delete {len(failures)} OSS objects") from failures[0]
        return
    for key in object_keys:
        (IMAGES_DIR / key).unlink(missing_ok=True)


def get_image_url(object_key: str) -> str:
    """根据 object key 生成浏览器可直接加载的 URL。"""
    if not object_key:
        return ""
    bucket = _get_bucket("public")
    if bucket:
        return bucket.sign_url("GET", object_key, settings.oss_url_expire_seconds)
    return f"/media/{object_key}"


def get_asset_url(asset_path: str) -> str:
    """Return a short-lived URL for a frontend asset stored in OSS."""
    normalized = asset_path.strip().lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise ValueError("invalid asset path")
    key = f"{settings.oss_asset_prefix.strip('/')}/{normalized}"
    bucket = _get_bucket("public")
    if bucket:
        return bucket.sign_url("GET", key, settings.oss_url_expire_seconds)
    return f"/assets/{normalized}"
