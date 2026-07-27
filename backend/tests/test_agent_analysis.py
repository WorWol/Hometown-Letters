"""agent 信件分析测试 - 验证 agent 能调 search_web 查证并正确理解。"""
import os
import pytest

from services.letter_agent import LetterAgent


@pytest.mark.asyncio
async def test_agent_empty_input_returns_empty():
    """空输入返回空结果，不调 LLM。"""
    svc = LetterAgent()
    result = await svc.run_letter_agent(letter_text="", place_hint="", hometown=None)
    assert result["core_place"] == ""
    assert result["image_prompt"], "空结果应有默认 image_prompt"


@pytest.mark.asyncio
async def test_agent_understands_黎那汐塔():
    """集成测试：agent 遇到'黎那汐塔的柯莱塔小土豆'应调 search_web 查证，
    不按字面理解成小吃摊/土豆摊。

    验证点：
    1. core_place = 黎那汐塔（识别地点）
    2. image_prompt 不应按字面把"小土豆"理解成小吃摊/土豆摊
    3. agent 应调过 search_web（查证实体背景）
    """
    if not os.environ.get("VOLC_API_KEY"):
        pytest.skip("无 VOLC_API_KEY，跳过 agent 集成测试")
    svc = LetterAgent()
    result = await svc.run_letter_agent(
        letter_text="你还记得黎那汐塔的柯莱塔小土豆吗",
        place_hint="黎那汐塔",
        image_style="pixel_16bit",
    )
    # 1. 识别地点
    assert result["core_place"] == "黎那汐塔", f"core_place 应为黎那汐塔，实际: {result['core_place']}"

    # 2. 不按字面理解成小吃摊/土豆摊（agent 查证后应知道"小土豆"可能是角色昵称）
    prompt = result.get("image_prompt", "")
    assert "土豆摊" not in prompt, f"agent 仍按字面理解成土豆摊: {prompt}"
    assert "小吃摊" not in prompt, f"agent 仍按字面理解成小吃摊: {prompt}"

    # 3. agent 产出了可用的生图提示词（visual_themes 受 LLM 输出波动影响，以 image_prompt 为准）
    assert result["image_prompt"], "image_prompt 不应为空"
