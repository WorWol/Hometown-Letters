"""用户上传参考图的后端校验测试。"""
from io import BytesIO

from PIL import Image

from services.image_service import ImageService


def _image_bytes(format_name: str = "PNG") -> bytes:
    image = Image.new("RGB", (128, 128), (220, 220, 220))
    output = BytesIO()
    image.save(output, format=format_name)
    return output.getvalue()


def test_uploaded_reference_accepts_real_png():
    assert ImageService.validate_reference_image(_image_bytes()) == (True, "")


def test_uploaded_reference_rejects_fake_image_bytes():
    valid, reason = ImageService.validate_reference_image(b"not-an-image")
    assert not valid
    assert reason == "参考图不是有效的图片文件"


def test_uploaded_reference_rejects_oversized_payload():
    valid, reason = ImageService.validate_reference_image(b"x" * (ImageService.MAX_REFERENCE_IMAGE_BYTES + 1))
    assert not valid
    assert reason == "参考图不能超过 10 MB"
