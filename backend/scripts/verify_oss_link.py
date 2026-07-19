"""Verify local-machine OSS upload, read, and delete with one temporary object."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import oss2

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402
from services.image_storage import validate_storage_config  # noqa: E402


def main() -> None:
    if settings.storage_backend.lower() != "oss":
        raise SystemExit("请先在 .env 设置 STORAGE_BACKEND=oss")
    validate_storage_config()

    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    bucket = oss2.Bucket(auth, settings.oss_upload_endpoint, settings.oss_bucket_name)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Keep the probe under a path allowed by the project's RAM policy.
    key = f"postcards/_connection-check/{suffix}.txt"
    payload = b"hometown-letters oss connection ok\n"
    try:
        put_result = bucket.put_object(
            key,
            payload,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        if not 200 <= put_result.status < 300:
            raise RuntimeError(f"上传失败: HTTP {put_result.status}")
        result = bucket.get_object(key)
        actual = result.read()
        if actual != payload:
            raise RuntimeError("读取内容与上传内容不一致")
        print(f"PASS upload/read: {settings.oss_bucket_name}/{key}")
    finally:
        bucket.delete_object(key)
        print("PASS delete: 临时探针对象已清理")


if __name__ == "__main__":
    main()
