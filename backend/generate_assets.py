"""生成像素风 UI 素材 — 信封、信纸、邮箱"""
import asyncio
import os
import sys
from io import BytesIO
from PIL import Image
import httpx

# 确保能找到 backend 模块
sys.path.insert(0, os.path.dirname(__file__))
from config import settings
from services.image_service import ImageService

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "assets")

ASSET_PROMPTS = {
    "env_envelope_closed.png": (
        "A pixel art envelope icon that fills the entire frame, front view, "
        "no empty space around edges, cream/beige envelope body with dark brown "
        "fold lines forming a V-shape, a bright red square stamp in the upper-right "
        "with a small postmark circle, warm vintage paper texture details visible, "
        "a dark brown border frames the image. Dense pixel art with a dark warm "
        "background filling all space, 16-bit SNES era game UI sprite style, "
        "visible 4x4 pixel grid, no transparency, no white void areas."
    ),
    "env_envelope_open.png": (
        "A pixel art opened envelope that fills the entire canvas, front view, "
        "the triangular flap opened upward revealing a light cream letter paper "
        "with thin blue horizontal ruled lines inside, envelope body in warm beige "
        "with visible crease marks, a popped red stamp still visible on the flap, "
        "edges of the letter paper visible with handwritten-style scribble marks. "
        "No empty space, the subject occupies the whole image from edge to edge. "
        "Dense 16-bit pixel art game sprite, visible pixel grid, dark warm "
        "background filling all remaining space, no transparency, no white void."
    ),
    "env_letter_paper.png": (
        "A dense pixel art writing paper texture that fills the entire frame, "
        "top-down flat view, off-white aged parchment with pronounced yellow-brown "
        "edges, subtle horizontal ruled lines in faded blue across every row, "
        "slight paper grain texture visible, a few ink blot speckles scattered "
        "naturally, slightly darker worn corners. No empty margins, the pattern "
        "continues edge to edge with no white void. 16-bit SNES era game UI "
        "texture, visible pixel grid, no transparency."
    ),
    "env_mailbox.png": (
        "A pixel art red traditional Japanese post mailbox that fills most of "
        "the frame, front view with slight angle, bright vermilion red cylindrical "
        "body, dark grey metal base and top cap, white rectangular mail slot on "
        "the front, small collection time plate visible. The mailbox subject takes "
        "up at least 70 percent of the image area, surrounded by a dark warm-toned "
        "background filling all empty space. Dense 16-bit pixel art game sprite, "
        "visible pixel grid, no transparency, no white void areas."
    ),
}


def auto_crop_to_content(img: Image.Image) -> Image.Image:
    """自动裁剪到非背景内容区域（去除透明/白色边缘）"""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    # 获取 alpha 通道，若没有则从 RGB 推算
    r, g, b, a = img.split()
    # 非透明且非近乎白色（R+G+B < 700）的像素视为内容
    # 用 alpha 通道：alpha > 10 即有内容
    alpha_arr = a.load() if a else None
    rgb_arr = img.load()
    w, h = img.size

    # 找到内容边界框
    left, top, right, bottom = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            if alpha_arr:
                px_a = alpha_arr[x, y] if hasattr(alpha_arr, '__getitem__') else a.getpixel((x, y))
            else:
                px_a = 255
            rv, gv, bv = img.getpixel((x, y))[:3]
            is_content = px_a > 15 and (rv + gv + bv) < 720  # 非几乎白色
            if is_content:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if left >= right or top >= bottom:
        # 未找到内容区域，返回原图
        return img

    # 加一点 padding
    pad = 8
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w, right + pad)
    bottom = min(h, bottom + pad)

    return img.crop((left, top, right, bottom))


async def download_url(url: str) -> bytes:
    """下载生成的图片"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def generate_one(image_svc: ImageService, filename: str, prompt: str):
    """生成一张素材并保存"""
    outpath = os.path.join(ASSETS_DIR, filename)

    print(f"  [GEN] {filename} ...")
    try:
        result = await image_svc.generate(prompt, size="HD")
        if not result.get("ok"):
            print(f"  [FAIL] {filename}: {result.get('error', 'unknown')}")
            return False

        url = result.get("url", "")
        if not url:
            print(f"  [FAIL] {filename}: no URL returned")
            return False

        print(f"  [DL]  {filename} <- {url[:60]}...")
        img_bytes = await download_url(url)

        img = Image.open(BytesIO(img_bytes))
        orig_w, orig_h = img.size
        print(f"  [RAW] {orig_w}x{orig_h}")

        if img.mode != "RGBA":
            img = img.convert("RGBA")

        # 自动裁剪白边/透明区域
        cropped = auto_crop_to_content(img)
        crop_w, crop_h = cropped.size
        if (crop_w, crop_h) != (orig_w, orig_h):
            print(f"  [CROP] {orig_w}x{orig_h} -> {crop_w}x{crop_h} ({((1 - crop_w*crop_h/(orig_w*orig_h))*100):.0f}% trimmed)")

        # 缩放到 512px 宽（保持比例），NEAREST 保留像素风
        new_w = 512
        ratio = new_w / crop_w
        new_h = max(1, int(crop_h * ratio))
        img = cropped.resize((new_w, new_h), Image.NEAREST)

        img.save(outpath, "PNG")
        file_size = os.path.getsize(outpath)
        print(f"  [OK]  {filename} ({img.width}x{img.height}, {file_size/1024:.1f}KB)")
        return True

    except Exception as e:
        import traceback
        print(f"  [ERR] {filename}: {e}")
        traceback.print_exc()
        return False


async def main():
    print("=" * 50)
    print("故乡来信 · 像素风 UI 素材生成")
    print("=" * 50)
    print(f"模型: {settings.volc_model}")
    print(f"输出: {ASSETS_DIR}")
    print()

    os.makedirs(ASSETS_DIR, exist_ok=True)
    image_svc = ImageService()

    ok = 0
    fail = 0
    for filename, prompt in ASSET_PROMPTS.items():
        success = await generate_one(image_svc, filename, prompt)
        if success:
            ok += 1
        else:
            fail += 1

    print()
    print(f"完成: {ok} OK, {fail} FAIL")

if __name__ == "__main__":
    asyncio.run(main())
