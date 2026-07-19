"""Upload frontend bitmap assets to the configured OSS bucket.

Usage (from the repository root):
    python3 backend/scripts/upload_frontend_assets.py
"""
from __future__ import annotations

import mimetypes
import sys
from pathlib import Path

import oss2

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402
from services.image_storage import validate_storage_config  # noqa: E402


def main() -> None:
    if settings.storage_backend.lower() != "oss":
        raise SystemExit("请先在 .env 设置 STORAGE_BACKEND=oss")
    validate_storage_config()

    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    bucket = oss2.Bucket(auth, settings.oss_upload_endpoint, settings.oss_bucket_name)
    assets_root = PROJECT_DIR / "frontend" / "assets"
    prefix = settings.oss_asset_prefix.strip("/") or "assets"
    files = sorted(path for path in assets_root.rglob("*") if path.is_file())
    if not files:
        raise SystemExit(f"素材目录为空: {assets_root}")

    for path in files:
        relative = path.relative_to(assets_root).as_posix()
        key = f"{prefix}/{relative}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as source:
            result = bucket.put_object(
                key,
                source,
                headers={
                    "Content-Type": content_type,
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        if not 200 <= result.status < 300:
            raise RuntimeError(f"上传失败: {key}, HTTP {result.status}")
        print(f"uploaded {key}")

    print(f"完成：上传 {len(files)} 个前端素材到 {settings.oss_bucket_name}/{prefix}/")


if __name__ == "__main__":
    main()
