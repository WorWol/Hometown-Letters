"""应用图片和前端素材的唯一存储入口。"""
from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

import aiofiles
from PIL import Image

from config import settings

IMAGES_DIR = Path(__file__).resolve().parent / "generated_images"
IMAGES_DIR.mkdir(exist_ok=True)
_buckets: dict[str, object] = {}


def validate_config() -> None:
    backend = settings.storage_backend.lower()
    if backend not in {"local", "oss"}:
        raise RuntimeError(f"STORAGE_BACKEND must be local or oss, got: {settings.storage_backend}")
    if backend == "oss":
        required = {
            "OSS_ACCESS_KEY_ID": settings.oss_access_key_id,
            "OSS_ACCESS_KEY_SECRET": settings.oss_access_key_secret,
            "OSS_UPLOAD_ENDPOINT": settings.oss_upload_endpoint,
            "OSS_PUBLIC_ENDPOINT": settings.oss_public_endpoint,
            "OSS_BUCKET_NAME": settings.oss_bucket_name,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError("OSS storage configuration is missing: " + ", ".join(missing))


def _bucket(kind: str):
    if settings.storage_backend.lower() != "oss":
        return None
    if kind not in {"upload", "public"}:
        raise ValueError(f"unknown storage bucket: {kind}")
    validate_config()
    if kind not in _buckets:
        import oss2

        endpoint = settings.oss_upload_endpoint if kind == "upload" else settings.oss_public_endpoint
        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        _buckets[kind] = oss2.Bucket(auth, endpoint, settings.oss_bucket_name)
    return _buckets[kind]


def object_exists(key: str) -> bool:
    if not key:
        return False
    bucket = _bucket("upload")
    if bucket:
        return bool(bucket.object_exists(key))
    return (IMAGES_DIR / key).is_file()


async def object_exists_async(key: str) -> bool:
    """异步检查对象是否存在，避免 OSS SDK 阻塞请求事件循环。"""
    return await asyncio.to_thread(object_exists, key)


def _encode_webp(source: Image.Image, size: int, quality: int) -> bytes:
    image = source.copy()
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    output = BytesIO()
    image.save(output, format="WEBP", quality=quality, method=6)
    return output.getvalue()


def image_keys(user_id: int, image_id: str) -> dict[str, str]:
    prefix = settings.oss_object_prefix.strip("/") or "postcards"
    return {name: f"{prefix}/{user_id}/{image_id}/{name}.webp" for name in ("thumb", "card", "original")}


def reference_image_key(user_id: int, image_id: str) -> str:
    prefix = settings.oss_object_prefix.strip("/") or "postcards"
    return f"{prefix}/{user_id}/{image_id}/reference.webp"


async def save_images(user_id: int, image_id: str, data: bytes) -> dict[str, str]:
    with Image.open(BytesIO(data)) as source:
        variants = {
            "thumb": _encode_webp(source, 480, 78),
            "card": _encode_webp(source, 1200, 86),
            "original": _encode_webp(source, 2048, 90),
        }

    keys = image_keys(user_id, image_id)
    bucket = _bucket("upload")
    written: list[str] = []
    try:
        for name, payload in variants.items():
            key = keys[name]
            if bucket:
                result = await asyncio.to_thread(
                    bucket.put_object,
                    key,
                    payload,
                    headers={"Content-Type": "image/webp", "Cache-Control": "private, max-age=31536000, immutable"},
                )
                if not 200 <= result.status < 300:
                    raise RuntimeError(f"OSS upload failed: {key}, HTTP {result.status}")
            else:
                path = IMAGES_DIR / key
                path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(path, "wb") as output:
                    await output.write(payload)
            written.append(key)
    except Exception:
        await delete_images({name: key for name, key in keys.items() if key in written})
        raise
    return keys


async def save_reference_image(user_id: int, image_id: str, data: bytes) -> str:
    key = reference_image_key(user_id, image_id)
    with Image.open(BytesIO(data)) as source:
        payload = _encode_webp(source, 2048, 90)
    bucket = _bucket("upload")
    if bucket:
        result = await asyncio.to_thread(
            bucket.put_object,
            key,
            payload,
            headers={"Content-Type": "image/webp", "Cache-Control": "private, max-age=31536000, immutable"},
        )
        if not 200 <= result.status < 300:
            raise RuntimeError(f"reference image upload failed: {key}, HTTP {result.status}")
    else:
        path = IMAGES_DIR / key
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as output:
            await output.write(payload)
    return key


async def delete_images(keys: dict[str, str]) -> None:
    object_keys = [key for key in keys.values() if key]
    if not object_keys:
        return
    bucket = _bucket("upload")
    if bucket:
        results = await asyncio.gather(
            *(asyncio.to_thread(bucket.delete_object, key) for key in object_keys),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            raise RuntimeError(f"failed to delete {len(failures)} storage objects") from failures[0]
        return
    for key in object_keys:
        (IMAGES_DIR / key).unlink(missing_ok=True)


def image_url(object_key: str) -> str:
    if not object_key:
        return ""
    if object_key.startswith(("http://", "https://", "data:", "blob:")):
        return object_key
    bucket = _bucket("public")
    if bucket:
        return bucket.sign_url("GET", object_key, settings.oss_url_expire_seconds)
    return f"/media/{object_key}"


def asset_url(asset_path: str) -> str:
    normalized = asset_path.strip().lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise ValueError("invalid asset path")
    prefix = settings.oss_asset_prefix.strip("/") or "assets"
    bucket = _bucket("public")
    if bucket:
        return bucket.sign_url("GET", f"{prefix}/{normalized}", settings.oss_url_expire_seconds)
    return f"/assets/{normalized}"
