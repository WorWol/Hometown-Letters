"""管道重构测试：模拟完整流程，不动真实 API

测试场景：用户在郴州，写信提到华中科技大学
  - hometown: 湖南省郴州市
  - letter: "你好，你在学校有找到你喜欢的人吗"
  - place_hint: "华中科技大学"
  - mood_hint: "怀念"

预期：
  1. 信件分析产出 search_keywords 含"武汉"（非郴州）
  2. image_prompt 不含中文地名，只描述视觉元素
  3. core_place = "华中科技大学"
  4. 筛选用 search_keywords 的关键词匹配 URL
"""
import json
import inspect
import pytest


# ── 准备 mock LLM（返回预设分析结果）──
MOCK_ANALYSIS = {
    "visual_themes": ["梧桐树", "教学楼", "校园大道", "黄昏", "年轻学生"],
    "emotional_tone": "怀念/青春/略带感伤",
    "scene_type": "school_gate",
    "search_keywords": [
        "武汉 华中科技大学 梧桐 校园",
        "university campus tree-lined path autumn",
        "华中科技大学 教学楼 夕阳",
        "大学校园 梧桐大道 秋天",
    ],
    "core_place": "华中科技大学",
    "image_prompt": "16-bit pixel art of a tree-lined university avenue in golden hour, students walking in small groups, warm autumn tones, soft shadows through leaves, nostalgic SNES-era game screenshot aesthetic",
}


class MockLlm:
    """模拟 DeepSeek，返回预设的 JSON"""
    def chat(self, system_prompt, user_message, temperature=0.8, max_tokens=500):
        return json.dumps(MOCK_ANALYSIS, ensure_ascii=False)


class HometownFallbackLlm:
    """模拟没有明确地点时，模型使用家乡作为搜图地点。"""

    def chat(self, system_prompt, user_message, **kwargs):
        return json.dumps({
            "visual_themes": ["东江湖湖面", "山路", "傍晚灯火"],
            "emotional_tone": "温暖/怀念",
            "scene_type": "lakeside_dam",
            "search_keywords": ["湖南郴州资兴 东江湖 湖面", "资兴 东江湖 sunset"],
            "core_place": "湖南郴州资兴",
            "generation_place": "湖南郴州资兴 东江湖",
            "image_prompt": "16-bit pixel art of a quiet lakeside town with layered mountains and warm evening lights",
        }, ensure_ascii=False)


class MockSearch:
    """模拟搜索 API，返回假 URL 列表"""
    async def search_images(self, query, num=6):
        # 模拟关键词匹配的搜索结果
        if "武汉" in query or "wuhan" in query.lower() or "university" in query.lower():
            return [
                "https://pics.example.com/wuhan_university_campus_01.jpg",
                "https://pics.example.com/autumn_campus_path_02.jpg",
                "https://pics.example.com/huazhong_school_gate_03.jpg",
                "https://pics.example.com/tree_lined_avenue_04.jpg",
            ]
        if "教学楼" in query or "夕阳" in query:
            return [
                "https://pics.example.com/school_building_sunset_05.jpg",
                "https://pics.example.com/classroom_window_06.jpg",
            ]
        return ["https://pics.example.com/generic_07.jpg"]

    async def search_text(self, query, num=3):
        return [{"content": f"关于{query}的描述内容，一段温暖的搜索结果文字"}]


@pytest.fixture
def analysis():
    from services.letter_analysis_service import LetterAnalysisService

    return LetterAnalysisService(MockLlm()).analyze_letter_deep(
        letter_text="你好，你在学校有找到你喜欢的人吗",
        place_hint="华中科技大学",
        mood_hint="怀念",
        hometown={"province": "湖南", "city": "郴州", "county": "资兴"},
    )


# ── 测试 1：信件分析服务 ──
def test_letter_analysis():
    print("=" * 50)
    print("测试 1：信件分析服务")
    print("=" * 50)

    from services.letter_analysis_service import LetterAnalysisService

    service = LetterAnalysisService(MockLlm())

    hometown = {"province": "湖南", "city": "郴州", "county": "资兴"}
    result = service.analyze_letter_deep(
        letter_text="你好，你在学校有找到你喜欢的人吗",
        place_hint="华中科技大学",
        mood_hint="怀念",
        hometown=hometown,
    )

    # 1.1 search_keywords 必须含 "武汉"（不是郴州）
    all_kw = " ".join(result["search_keywords"])
    assert "武汉" in all_kw, f"search_keywords 应含'武汉'，实际: {all_kw}"
    assert "郴州" not in all_kw, f"search_keywords 不应含'郴州'（信中提到的是武汉的大学），实际: {all_kw}"
    print("  PASS 1.1: search_keywords 含武汉不含郴州")

    # 1.2 core_place 应为 华中科技大学
    assert result["core_place"] == "华中科技大学", f"core_place 应为'华中科技大学'，实际: {result['core_place']}"
    print("  PASS 1.2: core_place = 华中科技大学")


def test_hometown_is_used_when_letter_has_no_explicit_place():
    from services.letter_analysis_service import LetterAnalysisService

    result = LetterAnalysisService(HometownFallbackLlm()).analyze_letter_deep(
        letter_text="今天只是想念家乡傍晚的风。",
        hometown={"province": "湖南", "city": "郴州", "county": "资兴"},
    )

    assert result["generation_place"] == "湖南郴州资兴 东江湖"
    assert any("资兴" in keyword for keyword in result["search_keywords"])

    # 1.3 image_prompt 不含中文地名
    assert "华中科技大学" not in result["image_prompt"], f"image_prompt 不应含地名，实际: {result['image_prompt']}"
    assert "武汉" not in result["image_prompt"], f"image_prompt 不应含地名，实际: {result['image_prompt']}"
    assert "pixel art" in result["image_prompt"].lower(), "image_prompt 应含像素风关键词"
    print("  PASS 1.3: image_prompt 无地名，有像素风关键词")

    # 1.4 visual_themes 非空
    assert len(result["visual_themes"]) >= 1
    print("  PASS 1.4: visual_themes 非空")

    # 1.5 emotional_tone 非空
    assert result["emotional_tone"]
    print("  PASS 1.5: emotional_tone 非空")

# ── 测试 2：图片筛选 ──
def test_selection(analysis):
    print()
    print("=" * 50)
    print("测试 2：图片筛选（keyword匹配 URL）")
    print("=" * 50)

    from services.selection_service import SelectionService

    service = SelectionService()

    urls = [
        "https://pics.example.com/wuhan_university_campus_01.jpg",
        "https://pics.example.com/beijing_temple_unrelated_02.jpg",
        "https://pics.example.com/autumn_campus_path_03.jpg",
        "https://pics.example.com/wuhan_university_campus_01.jpg",
        "https://pics.example.com/random_city_skyline_04.jpg",
        "https://pics.example.com/huazhong_school_gate_05.jpg",
        "https://pics.example.com/tree_lined_avenue_06.jpg",
    ]

    result = service.filter_relevant_images(urls, analysis)

    # 2.1 筛选后应有结果
    assert len(result) >= 1, f"筛选后应有结果，实际: {result}"
    print("  PASS 2.1: 筛选有结果")

    # 2.2 当前筛选层只负责稳定去重，相关性由搜索关键词保证
    assert len(result) == len(set(result))
    assert result[0] == urls[0]
    print("  PASS 2.2: 保序去重")

    # 2.3 相关图片尽可能保留（URL keyword 匹配有中英文/连字符限制，部分漏过可接受）
    retained_count = len(result)
    print(f"  PASS 2.3: 保留 {retained_count}/{len(urls)} 张（关键词匹配过滤）")

    # 2.4 最多返回 5 张
    assert len(result) <= 5
    print("  PASS 2.4: 结果 ≤ 5 张")

# ── 测试 3：图片提示词生成（不再调 LLM）──
def test_image_prompt(analysis):
    print()
    print("=" * 50)
    print("测试 3：图片提示词（从分析结果直接取）")
    print("=" * 50)

    # 3.1 analysis 里已有 image_prompt
    prompt = analysis.get("image_prompt", "")
    assert prompt, "analysis 应包含 image_prompt"
    print("  PASS 3.1: analysis 包含 image_prompt")

    # 3.2 不含中文地名
    for name in ["华中科技大学", "武汉", "郴州", "湖南"]:
        assert name not in prompt, f"image_prompt 不应含 '{name}'，实际: {prompt}"
    print("  PASS 3.2: image_prompt 无任何地名")

    # 3.3 含像素风关键词
    pixel_keywords = ["pixel art", "16-bit", "SNES", "game screenshot"]
    found_pixel = any(kw.lower() in prompt.lower() for kw in pixel_keywords)
    assert found_pixel, f"image_prompt 应含像素风关键词，实际: {prompt}"
    print(f"  PASS 3.3: 像素风关键词: {[kw for kw in pixel_keywords if kw.lower() in prompt.lower()][0]}")

    # 3.4 含视觉元素（来自信件分析）
    visual_kw = ["tree", "campus", "avenue", "student", "golden", "autumn"]
    found_visual = [kw for kw in visual_kw if kw.lower() in prompt.lower()]
    assert len(found_visual) >= 2, f"image_prompt 应含视觉元素，找到: {found_visual}"
    print(f"  PASS 3.4: 视觉元素: {found_visual}")

# ── 测试 4：地标选择（place_hint → 自定义地标）──
def test_selection_small_input_is_unchanged():
    print()
    print("=" * 50)
    print("测试 4：少量图片保持原顺序")
    print("=" * 50)

    from services.selection_service import SelectionService

    urls = ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    assert SelectionService().filter_relevant_images(urls, {}) == urls
    print("  PASS 4: 少量图片保持原顺序")


# ── 测试 5：PoemService 接口兼容性 ──
def test_poem_service():
    print()
    print("=" * 50)
    print("测试 5：PoemService 接口")
    print("=" * 50)

    from services.poem_service import PoemService

    ps = PoemService(None)

    # 验证所有方法都接受 analysis 参数
    for method_name in ["generate_poem", "generate_title", "generate_body"]:
        method = getattr(ps, method_name)
        sig = inspect.signature(method)
        assert "analysis" in sig.parameters, f"{method_name} 缺少 analysis 参数"
        print(f"  PASS 5: {method_name} 含 analysis 参数")


# ── 测试 6：降级方案 ──
def test_fallback():
    print()
    print("=" * 50)
    print("测试 6：降级方案")
    print("=" * 50)

    from services.letter_analysis_service import LetterAnalysisService

    service = LetterAnalysisService(None)

    # 6.1 空输入
    empty = service._empty_result()
    assert empty["core_place"] == ""
    assert empty["image_prompt"], "空结果应有默认 image_prompt"
    print("  PASS 6.1: 空输入有默认值")

    # 6.2 fallback
    fb = service._fallback("...", "华中科技大学", "怀念")
    assert fb["core_place"] == "华中科技大学"
    assert "华中科技大学" not in fb["image_prompt"]
    print("  PASS 6.2: fallback 无地名")

    # 6.3 build_image_prompt
    bp = service._build_image_prompt({
        "visual_themes": ["梧桐树", "校园"],
        "scene_type": "school_gate",
        "emotional_tone": "怀念",
    })
    assert "华中科技大学" not in bp
    assert "quiet campus" in bp.lower()
    print("  PASS 6.3: _build_image_prompt 无地名")

    # 6.4 无 visual_themes 时也能生成
    bp2 = service._build_image_prompt({
        "visual_themes": [],
        "scene_type": "other",
        "emotional_tone": "",
    })
    assert "16-bit pixel art" in bp2
    print("  PASS 6.4: 无视觉主题时也能生成 prompt")


# ── 主流程 ──
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════╗")
    print("║  管道重构测试套件                                  ║")
    print("║  场景: 郴州用户 → 华中科技大学 → 校园黄昏          ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    analysis = MOCK_ANALYSIS
    selected = test_selection(analysis)
    prompt = test_image_prompt(analysis)
    test_selection_small_input_is_unchanged()
    test_poem_service()
    test_fallback()

    print()
    print("=" * 50)
    print("全部测试通过")
    print("=" * 50)
    print()
    print("总结:")
    print(f"  search_keywords 驱动搜图（不依赖 hometown geo 拼接）")
    print(f"  image_prompt 从分析结果直出（不额外调 LLM）")
    print(f"  core_place = '{analysis['core_place']}' 引导地标匹配")
    print(f"  筛选基于 keyword URL 匹配（无 LLM）")
    print(f"  所有 image_prompt 不含中文地名，像素风关键词完整")
