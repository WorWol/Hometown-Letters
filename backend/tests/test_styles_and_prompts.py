"""图像风格与提示词管理的单元测试。"""
import pytest

from services.style_service import (
    DEFAULT_STYLE_ID, STYLES, get_analysis_hint, get_style, get_style_prompt, list_styles,
)
from services import prompt_service


# ── 风格服务 ──

class TestStyleService:
    def test_list_styles_returns_all(self):
        styles = list_styles()
        assert len(styles) == len(STYLES)
        for s in styles:
            assert "id" in s and "label" in s
            assert "style_prompt" not in s  # 详细信息不暴露给前端

    def test_get_style_returns_default_for_unknown(self):
        style = get_style("nonexistent")
        assert style["id"] == DEFAULT_STYLE_ID

    def test_get_style_returns_default_for_none(self):
        style = get_style(None)
        assert style["id"] == DEFAULT_STYLE_ID

    def test_get_style_prompt_matches_style(self):
        for s in STYLES:
            assert get_style_prompt(s["id"]) == s["style_prompt"]

    def test_get_analysis_hint_matches_style(self):
        for s in STYLES:
            assert get_analysis_hint(s["id"]) == s["analysis_hint"]

    def test_default_style_is_pixel(self):
        assert DEFAULT_STYLE_ID == "pixel_16bit"
        assert get_style(None)["id"] == "pixel_16bit"

    def test_all_styles_have_required_fields(self):
        for s in STYLES:
            assert s["id"], "missing id"
            assert s["label"], "missing label"
            assert s["style_prompt"], "missing style_prompt"
            assert s["analysis_hint"], "missing analysis_hint"


# ── 提示词服务 ──

class TestPromptService:
    def test_get_prompt_returns_default_before_load(self):
        # 重置缓存状态
        prompt_service._cache.clear()
        prompt_service._loaded = False
        content = prompt_service.get_prompt("poem")
        assert "诗人" in content

    def test_get_prompt_with_style_hint_replacement(self):
        prompt_service._cache.clear()
        prompt_service._loaded = False
        content = prompt_service.get_prompt("letter_analysis", style_hint="WATERCOLOR")
        assert "WATERCOLOR" in content
        assert "{STYLE_HINT}" not in content

    def test_get_prompt_unknown_key_returns_empty(self):
        prompt_service._cache.clear()
        prompt_service._loaded = False
        assert prompt_service.get_prompt("nonexistent") == ""

    def test_all_prompt_defaults_have_content(self):
        for key, meta in prompt_service.PROMPT_DEFAULTS.items():
            assert meta["content"], f"{key} has empty default content"
            assert meta["label"], f"{key} has empty label"

    def test_seven_prompts_registered(self):
        expected = {"letter_analysis", "poem", "title", "body", "image_prompt", "batch_memory", "profile"}
        assert set(prompt_service.PROMPT_DEFAULTS.keys()) == expected

    def test_letter_analysis_has_style_hint_placeholder(self):
        content = prompt_service.PROMPT_DEFAULTS["letter_analysis"]["content"]
        assert "{STYLE_HINT}" in content

    @pytest.mark.asyncio
    async def test_override_and_reset_cycle(self, tmp_path, monkeypatch):
        """测试覆盖和重置的完整周期（使用真实 SQLite）。"""
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from db.models import Base, PromptOverride
        from sqlalchemy import select, delete

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test_prompts.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # 替换 prompt_service 的 async_session
        monkeypatch.setattr(prompt_service, "async_session", session_factory)

        # 加载缓存（空）
        await prompt_service.load_cache()
        assert not prompt_service._cache

        # 设置覆盖
        await prompt_service.set_override("poem", "覆盖的诗歌提示词", "developer1")
        assert prompt_service._cache["poem"] == "覆盖的诗歌提示词"
        assert prompt_service.get_prompt("poem") == "覆盖的诗歌提示词"

        # 重置
        await prompt_service.reset_override("poem")
        assert "poem" not in prompt_service._cache
        assert "诗人" in prompt_service.get_prompt("poem")  # 回到默认

        # 验证 DB 中确实删除了
        async with session_factory() as db:
            result = await db.execute(select(PromptOverride).where(PromptOverride.key == "poem"))
            assert result.scalar_one_or_none() is None

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_list_prompts_returns_overridden_flag(self, tmp_path, monkeypatch):
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from db.models import Base

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test_prompts2.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(prompt_service, "async_session", session_factory)

        await prompt_service.load_cache()
        await prompt_service.set_override("title", "覆盖标题", "dev")

        prompts = await prompt_service.list_prompts()
        title_prompt = next(p for p in prompts if p["key"] == "title")
        assert title_prompt["overridden"] is True
        assert title_prompt["content"] == "覆盖标题"

        poem_prompt = next(p for p in prompts if p["key"] == "poem")
        assert poem_prompt["overridden"] is False
        assert poem_prompt["content"] == poem_prompt["defaultContent"]

        await engine.dispose()
