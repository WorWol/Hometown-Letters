"""测试火山引擎图像生成 — 生成信封素材"""

import os, sys, asyncio, httpx, json, base64, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# 使用备用 key（已充值）
API_KEY = "ark-88e5417b-2523-4d06-83cf-e8878124c866-d8a25"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 候选生图模型
CANDIDATE_MODELS = [
    ("doubao-seedream-4-0-250828",      "Seedream 4.0"),
]

# 实际需要的素材
PROMPTS = [
    {
        "name": "envelope_clean",
        "prompt": (
            "A single vintage envelope, front view, centered composition, "
            "cream-colored paper with subtle aged texture, "
            "delicate fold lines, a small elegant red wax seal, "
            "clean white background, soft studio lighting, "
            "the envelope takes up 80% of the frame, "
            "flat lay product photography style"
        ),
    },
    {
        "name": "stamp_vintage",
        "prompt": (
            "A single vintage postage stamp, square format, "
            "delicate illustration of a Chinese landscape with mountains and pine trees, "
            "aged paper texture, perforated edges clearly visible, "
            "muted red and green tones, warm nostalgic colors, "
            "clean white background, centered, "
            "the stamp fills most of the frame, "
            "collectible stamp photography style"
        ),
    },
    {
        "name": "letter_paper",
        "prompt": (
            "A seamless tileable aged paper texture, "
            "cream-colored vintage paper with subtle fiber patterns, "
            "very faint horizontal ruled lines, "
            "slight yellowing at the edges, "
            "delicate paper grain visible, "
            "warm parchment tones, no text or writing, "
            "clean flat scan of antique stationery, "
            "the texture should be evenly lit and seamless for tiling"
        ),
    },
]

OUTPUT_DIR = Path(__file__).parent.parent / "frontend" / "assets" / "generated"


async def generate_image(model: str, prompt: str, size: str = "2048x2048") -> dict:
    """调用火山引擎 images/generations API"""
    url = f"{BASE_URL}/images/generations"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "response_format": "url",
    }

    t0 = time.time()
    async with httpx.AsyncClient(timeout=120, proxy=None) as client:
        resp = await client.post(url, headers=headers, json=payload)
        elapsed = time.time() - t0

        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:300]}", "elapsed": elapsed}

        data = resp.json()
        choices = data.get("data", [])
        if choices:
            return {
                "ok": True,
                "url": choices[0].get("url", ""),
                "elapsed": elapsed,
            }
        return {"ok": False, "error": f"No data: {json.dumps(data, ensure_ascii=False)[:300]}", "elapsed": elapsed}


async def download_image(url: str, filepath: Path) -> bool:
    """下载图片到本地"""
    async with httpx.AsyncClient(timeout=30, proxy=None) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            filepath.write_bytes(resp.content)
            return True
    return False


async def test_all():
    """测试所有模型 × prompt 组合"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for model_id, model_name in CANDIDATE_MODELS:
        for prompt_cfg in PROMPTS:
            label = f"{model_name} × {prompt_cfg['name']}"
            print(f"\n{'='*60}")
            print(f"🧪 测试: {label}")
            print(f"   模型: {model_id}")

            result = await generate_image(model_id, prompt_cfg["prompt"])
            result["model"] = model_id
            result["model_name"] = model_name
            result["prompt_name"] = prompt_cfg["name"]
            result["label"] = label

            if result["ok"]:
                fname = f"{model_id.split('/')[-1]}_{prompt_cfg['name']}.png"
                fpath = OUTPUT_DIR / fname
                if await download_image(result["url"], fpath):
                    size_kb = fpath.stat().st_size / 1024
                    print(f"   ✅ 成功! 耗时: {result['elapsed']:.1f}s, 大小: {size_kb:.0f}KB, 文件: {fname}")
                    result["file"] = str(fpath)
                    result["size_kb"] = size_kb
                else:
                    print(f"   ⚠️ 生成成功但下载失败")
                    result["download_ok"] = False
            else:
                print(f"   ❌ 失败: {result['error'][:200]}")

            results.append(result)

    # 汇总
    print(f"\n{'='*60}")
    print("📊 测试汇总")
    print(f"{'='*60}")
    success = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    print(f"成功: {len(success)}, 失败: {len(failed)}")
    for r in success:
        print(f"  ✅ {r['label']}: {r['elapsed']:.1f}s, {r.get('size_kb', '?')}KB → {Path(r.get('file', '?')).name}")
    for r in failed:
        print(f"  ❌ {r['label']}: {r['error'][:100]}")

    return results


if __name__ == "__main__":
    asyncio.run(test_all())
