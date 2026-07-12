#!/usr/bin/env python3
"""后端生图 API 单测
测试范围：
1. ImageService.generate() — 调火山引擎生图 + 下载缓存
2. PoemService.generate_image_prompt() — LLM 生成提示词
3. 完整链路：提示词 → 生图 → 下载缓存
"""
import os
import sys
import io
import asyncio
from pathlib import Path

# 确保当前目录在 path 中
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from store import store
from services.poem_service import PoemService
from services.image_service import ImageService


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  ✅ {name}")

    def fail(self, name: str, detail: str = ""):
        self.failed += 1
        msg = f"  ❌ {name}" + (f" — {detail}" if detail else "")
        self.errors.append(msg)
        print(msg)

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"结果: {self.passed}/{total} 通过, {self.failed} 失败")
        if self.errors:
            for e in self.errors:
                print(e)
        return self.failed == 0


r = TestResult()

# ═══════════════════════════════════════
# 测试 1: 配置检查
# ═══════════════════════════════════════
print("\n── 测试 1: 配置检查 ──")
if settings.volc_api_key and len(settings.volc_api_key) > 10:
    r.ok("VOLC_API_KEY 已配置")
else:
    r.fail("VOLC_API_KEY", "key 为空或过短")

if settings.volc_model:
    r.ok(f"VOLC_MODEL = {settings.volc_model}")
else:
    r.fail("VOLC_MODEL", "模型名称为空")

print(f"  📝 image_gen_style = {settings.image_gen_style[:80]}...")

# 验证风格描述是英文（不含中文）
if any('\u4e00' <= c <= '\u9fff' for c in settings.image_gen_style):
    r.fail("风格描述是英文", "仍含中文字符，可能影响模型理解")
else:
    r.ok("风格描述全英文")


# ═══════════════════════════════════════
# 测试 2: PoemService 提示词生成
# ═══════════════════════════════════════
print("\n── 测试 2: 提示词生成 ──")
poem_svc = PoemService()

# 测试地标
test_landmarks = [
    {"name": "秀流公园", "description": "资兴市中心的老公园，梧桐树成荫，老人下棋",
     "scene_type": "park"},
    {"name": "东江湖", "description": "湖南郴州的大型水库，晨雾缭绕，被誉为东方瑞士",
     "scene_type": "lakeside_dam"},
    {"name": "老街", "description": "资兴老街，青石板路，老式店铺",
     "scene_type": "bridge_roadside"},
]

for lm in test_landmarks:
    try:
        prompt = poem_svc.generate_image_prompt(lm, "温暖的夏日午后")
        if prompt and len(prompt) > 20:
            # 检查关键特征
            has_pixel = "pixel" in prompt.lower()
            has_retro = "retro" in prompt.lower() or "16-bit" in prompt.lower() or "game" in prompt.lower()
            no_painterly = "painterly" not in prompt.lower()

            flags = []
            if not has_pixel: flags.append("缺少 pixel")
            if not has_retro: flags.append("缺少 retro/16-bit")
            if not no_painterly: flags.append("含 painterly")

            if flags:
                r.fail(f"{lm['name']} 提示词", ", ".join(flags))
            else:
                r.ok(f"{lm['name']} 提示词")
            print(f"     → {prompt[:120]}...")
        else:
            r.fail(f"{lm['name']} 提示词", "生成内容过短")
    except Exception as e:
        r.fail(f"{lm['name']} 提示词", str(type(e).__name__) + ": " + str(e)[:100])


# ═══════════════════════════════════════
# 测试 3: ImageService 生成图片
# ═══════════════════════════════════════
print("\n── 测试 3: 火山引擎生图 ──")
img_svc = ImageService()

async def test_generate():
    """用真实 API 测试生图"""
    landmark = {"name": "东江湖", "description": "晨雾缭绕的湖面，远处青山隐隐", "scene_type": "lakeside_dam"}
    prompt = poem_svc.generate_image_prompt(landmark, "清晨薄雾")

    print(f"  提示词: {prompt[:150]}...")

    result = await img_svc.generate(prompt, size="2K")
    if result.get("ok"):
        url = result.get("url", "")
        r.ok(f"生图成功")
        print(f"  URL: {url[:80]}...")

        # 测试下载缓存
        data = await ImageService.download_image_bytes(url)
        if data and len(data) > 1000:
            pc_id = "test-cache-001"
            store.cache_image(pc_id, data, "image/jpeg")
            cached = store.get_cached_image(pc_id)
            if cached and cached[0] == data:
                r.ok(f"图片下载缓存 ({len(data)/1024:.0f} KB)")
            else:
                r.fail("图片缓存", "缓存读取不一致")
        else:
            r.fail("图片下载", f"下载数据异常: {len(data) if data else 0} bytes")
    else:
        r.fail("生图", result.get("error", "unknown")[:200])


# ═══════════════════════════════════════
# 测试 4: 图片代理端点逻辑验证
# ═══════════════════════════════════════
print("\n── 测试 4: 图片缓存存取逻辑 ──")

# 清空测试缓存
store._image_cache.clear()

test_id = "unit-test-pc-001"
test_data = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 1000  # 模拟 JPEG
store.cache_image(test_id, test_data, "image/jpeg")

cached = store.get_cached_image(test_id)
if cached is not None:
    r.ok("缓存写入成功")
    data, ct = cached
    if data == test_data:
        r.ok("缓存读取数据一致")
    else:
        r.fail("缓存读取", "数据不一致")
    if ct == "image/jpeg":
        r.ok("content_type 正确")
    else:
        r.fail("content_type", f"期望 image/jpeg, 实际 {ct}")
else:
    r.fail("缓存写入", "get_cached_image 返回 None")

# 测试不存在的 key
missing = store.get_cached_image("nonexistent-id")
if missing is None:
    r.ok("不存在 key 返回 None")
else:
    r.fail("不存在 key", "应该返回 None")

# 测试覆盖写入
test_data2 = b'\x89PNG\r\n\x1a\n' + b'\x00' * 500
store.cache_image(test_id, test_data2, "image/png")
cached2 = store.get_cached_image(test_id)
if cached2 and cached2[0] == test_data2:
    r.ok("缓存覆盖写入")
else:
    r.fail("缓存覆盖", "覆盖后数据不一致")


# ═══════════════════════════════════════
# 汇总
# ═══════════════════════════════════════
success = r.summary()

if not success:
    sys.exit(1)

print("\n── 集成测试: 完整生图链路 ──")
asyncio.run(test_generate())
r.summary()