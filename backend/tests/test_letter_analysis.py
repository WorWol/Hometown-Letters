"""信件分析 agent 测试：验证 run_letter_agent 的输出解析与默认值。"""
import json
import pytest


class MockLlm:
    """模拟 agent 自主完成后的输出（不调工具，直接返回 JSON）。"""
    async def chat_with_tools(self, system_prompt, user_message, tools, tool_handler, **kwargs):
        return json.dumps({
            "reference_images": [{"url": "https://pics.example.com/campus.jpg", "role": "scene"}],
            "image_prompt": "16-bit pixel art of a tree-lined university avenue in golden hour, students walking, warm autumn tones, no watermark",
            "poem": "梧桐落叶满校园", "title": "校园黄昏", "body": "那天黄昏，梧桐树下...",
            "core_place": "华中科技大学", "generation_place": "武汉 华中科技大学",
            "emotional_tone": "怀念/青春/略带感伤", "visual_themes": ["梧桐树", "教学楼", "黄昏"],
        }, ensure_ascii=False)

    async def vision_describe(self, image_data_url, prompt):
        return "校园林荫道，梧桐树，黄昏光线"


class HometownFallbackLlm:
    """模拟没有明确地点时，agent 用家乡作为搜图地点。"""
    async def chat_with_tools(self, system_prompt, user_message, tools, tool_handler, **kwargs):
        return json.dumps({
            "reference_images": [{"url": "https://pics.example.com/lake.jpg", "role": "scene"}],
            "image_prompt": "16-bit pixel art of a quiet lakeside town with layered mountains and warm evening lights",
            "poem": "东江湖畔", "title": "湖畔暮色", "body": "傍晚的湖面...",
            "core_place": "湖南郴州资兴", "generation_place": "湖南郴州资兴 东江湖",
            "emotional_tone": "温暖/怀念", "visual_themes": ["东江湖湖面", "山路", "傍晚灯火"],
        }, ensure_ascii=False)

    async def vision_describe(self, image_data_url, prompt):
        return "湖畔小镇"


class MockSearch:
    async def search_images(self, query, num=6):
        return [{"url": "https://pics.example.com/scene.jpg", "title": "场景", "source": "test"}]

    async def search_text(self, query, num=3):
        return [{"content": f"关于{query}的描述"}]


@pytest.mark.asyncio
async def test_run_letter_agent_parses_output():
    """agent 输出被正确解析，字段齐全。"""
    from services.letter_agent import LetterAgent

    service = LetterAgent(llm=MockLlm(), search=MockSearch())
    result = await service.run_letter_agent(
        letter_text="你好，你在学校有找到你喜欢的人吗",
        place_hint="华中科技大学",
        mood_hint="怀念",
        hometown={"province": "湖南", "city": "郴州", "county": "资兴"},
    )

    # core_place 用 agent 输出
    assert result["core_place"] == "华中科技大学"
    assert result["generation_place"] == "武汉 华中科技大学"
    # reference_images 非空
    assert result["reference_images"], "reference_images 不应为空"
    assert result["reference_images"][0]["url"]
    # image_prompt 含视觉元素
    assert "pixel art" in result["image_prompt"].lower()
    # 其他字段
    assert result["emotional_tone"]
    assert result["visual_themes"]
    assert result["poem"]
    assert result["title"]
    assert result["body"]


@pytest.mark.asyncio
async def test_hometown_is_used_when_letter_has_no_explicit_place():
    """信件无明确地点时，agent 用家乡作为 generation_place。"""
    from services.letter_agent import LetterAgent

    result = await LetterAgent(llm=HometownFallbackLlm(), search=MockSearch()).run_letter_agent(
        letter_text="今天只是想念家乡傍晚的风。",
        hometown={"province": "湖南", "city": "郴州", "county": "资兴"},
    )

    assert result["generation_place"] == "湖南郴州资兴 东江湖"
    assert result["core_place"] == "湖南郴州资兴"
    assert result["image_prompt"]
    assert result["reference_images"]


@pytest.mark.asyncio
async def test_empty_input_returns_empty():
    """空输入返回空结果，不调 LLM。"""
    from services.letter_agent import LetterAgent

    result = await LetterAgent(llm=MockLlm(), search=MockSearch()).run_letter_agent(
        letter_text="", place_hint="", hometown=None,
    )
    assert result["core_place"] == ""
    assert result["image_prompt"], "空结果应有默认 image_prompt"
    assert result["reference_images"] == []


def test_build_image_prompt():
    """默认 image_prompt 构建（agent 没返回时的兜底）。

    兜底 prompt 不含画风/风格词（生图时由 generate_image 工具自动追加所选风格），
    只描述场景主体/构图景深/角色处理/光线色彩/氛围细节。
    """
    from services.letter_agent import LetterAgent

    service = LetterAgent(llm=None, search=MockSearch())

    # 空输入
    empty = service._empty_result()
    assert empty["core_place"] == ""
    assert empty["image_prompt"], "空结果应有默认 image_prompt"
    assert "场景主体" in empty["image_prompt"]

    # _build_image_prompt：结构化、含主题与情绪、不含画风词
    bp = service._build_image_prompt({
        "visual_themes": ["梧桐树", "校园"],
        "emotional_tone": "怀念",
    })
    assert "梧桐树" in bp and "校园" in bp, "应包含 visual_themes"
    assert "怀念" in bp, "应包含 emotional_tone"
    assert "场景主体" in bp and "构图与景深" in bp, "应为五段结构"
    assert "像素风" not in bp, "兜底 prompt 不应含画风词（风格由工具追加）"
    assert "华中科技大学" not in bp

    # 无 visual_themes 时也能生成
    bp2 = service._build_image_prompt({"visual_themes": [], "emotional_tone": ""})
    assert "场景主体" in bp2
    assert "像素风" not in bp2
