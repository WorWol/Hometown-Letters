"""图片服务的离线回归测试。

真实供应商调用属于手动集成测试，不应在 pytest 收集阶段执行。
"""
from __future__ import annotations

from services.image_service import ImageService
from storage import image_url


def test_normalize_image_size_aliases():
    assert ImageService._normalize_size("2K") == "2048x2048"
    assert ImageService._normalize_size("hd") == "1920x1920"
    assert ImageService._normalize_size("1536x1024") == "1536x1024"


def test_external_fallback_url_is_not_wrapped():
    url = "https://images.example.com/fallback.jpg"
    assert image_url(url) == url


def test_reference_image_key_uses_postcard_prefix(monkeypatch):
    monkeypatch.setattr("config.settings.oss_object_prefix", "postcards")
    from storage import reference_image_key

    assert reference_image_key(14, "pc-test") == "postcards/14/pc-test/reference.webp"


def test_encode_reference_image_uses_source_extension():
    encoded = ImageService.encode_reference_image(b"hello", "https://example.com/image.jpg?x=1")
    assert encoded.startswith("data:image/jpeg;base64,")


def test_local_image_id_uses_media_route(monkeypatch):
    monkeypatch.setattr("config.settings.storage_backend", "local")
    assert image_url("pc-test") == "/media/pc-test"
