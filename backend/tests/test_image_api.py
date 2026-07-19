"""图片存储的离线回归测试。"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from services import image_storage
from services.image_storage import (
    get_asset_url,
    get_image_url,
    image_variant_keys,
    save_image_variants,
    validate_storage_config,
)


def test_local_image_url_uses_media_prefix(monkeypatch):
    monkeypatch.setattr(image_storage.settings, "storage_backend", "local")
    assert get_image_url("postcards/1/pc-1/thumb.webp") == "/media/postcards/1/pc-1/thumb.webp"


def test_local_asset_url_keeps_frontend_path(monkeypatch):
    monkeypatch.setattr(image_storage.settings, "storage_backend", "local")
    assert get_asset_url("icons/icon_postcards.png") == "/assets/icons/icon_postcards.png"


def test_asset_path_rejects_traversal(monkeypatch):
    monkeypatch.setattr(image_storage.settings, "storage_backend", "local")
    try:
        get_asset_url("../.env")
    except ValueError:
        pass
    else:
        raise AssertionError("asset traversal must be rejected")


def test_local_storage_configuration_is_valid(monkeypatch):
    monkeypatch.setattr(image_storage.settings, "storage_backend", "local")
    validate_storage_config()


def test_image_keys_use_configured_prefix(monkeypatch):
    monkeypatch.setattr(image_storage.settings, "oss_object_prefix", "assets")
    assert image_variant_keys(7, "pc-test")["original"] == "assets/7/pc-test/original.webp"


def test_oss_configuration_requires_public_and_upload_endpoints(monkeypatch):
    monkeypatch.setattr(image_storage.settings, "storage_backend", "oss")
    monkeypatch.setattr(image_storage.settings, "oss_access_key_id", "id")
    monkeypatch.setattr(image_storage.settings, "oss_access_key_secret", "secret")
    monkeypatch.setattr(image_storage.settings, "oss_upload_endpoint", "internal")
    monkeypatch.setattr(image_storage.settings, "oss_public_endpoint", "")
    monkeypatch.setattr(image_storage.settings, "oss_bucket_name", "bucket")

    try:
        validate_storage_config()
    except RuntimeError as error:
        assert "OSS_PUBLIC_ENDPOINT" in str(error)
    else:
        raise AssertionError("missing public endpoint must fail validation")


async def test_image_variants_are_webp_and_keyed_by_user(tmp_path, monkeypatch):
    monkeypatch.setattr(image_storage, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(image_storage.settings, "storage_backend", "local")
    output = BytesIO()
    Image.new("RGB", (1600, 900), "#d8c4a8").save(output, format="JPEG")

    keys = await save_image_variants(7, "pc-test", output.getvalue())

    assert keys == {
        "thumb": "postcards/7/pc-test/thumb.webp",
        "card": "postcards/7/pc-test/card.webp",
        "original": "postcards/7/pc-test/original.webp",
    }
    for key in keys.values():
        assert (tmp_path / key).is_file()


async def test_oss_upload_sign_and_delete_flow(monkeypatch):
    class Result:
        status = 200

    class FakeBucket:
        def __init__(self):
            self.objects = {}

        def put_object(self, key, payload, headers=None):
            self.objects[key] = (payload, headers or {})
            return Result()

        def sign_url(self, method, key, expires):
            assert method == "GET"
            assert key in self.objects
            assert expires == 900
            return f"https://oss.example.test/{key}?signature=test"

        def delete_object(self, key):
            self.objects.pop(key, None)
            return Result()

    bucket = FakeBucket()
    monkeypatch.setattr(image_storage.settings, "storage_backend", "oss")
    monkeypatch.setattr(image_storage.settings, "oss_access_key_id", "id")
    monkeypatch.setattr(image_storage.settings, "oss_access_key_secret", "secret")
    monkeypatch.setattr(image_storage.settings, "oss_upload_endpoint", "internal")
    monkeypatch.setattr(image_storage.settings, "oss_public_endpoint", "public")
    monkeypatch.setattr(image_storage.settings, "oss_bucket_name", "bucket")
    monkeypatch.setattr(image_storage, "_get_bucket", lambda kind: bucket)

    output = BytesIO()
    Image.new("RGB", (900, 600), "#8da9c4").save(output, format="JPEG")
    keys = await save_image_variants(3, "pc-oss-test", output.getvalue())

    assert set(bucket.objects) == set(keys.values())
    assert get_image_url(keys["card"]).startswith("https://oss.example.test/")
    assert all(payload[1]["Content-Type"] == "image/webp" for payload in bucket.objects.values())

    await image_storage.delete_image_variants(keys)
    assert bucket.objects == {}
