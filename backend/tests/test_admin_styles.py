"""图像风格 DB 驱动与 admin CRUD 的单元测试。"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import admin
from db.models import Base, ImageStyle, User
from services import style_service


@pytest.fixture
async def db_session(monkeypatch):
    """内存 SQLite + monkeypatch admin/style_service 的 async_session。"""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(admin, "async_session", maker)
    monkeypatch.setattr(style_service, "async_session", maker)
    async with maker() as db:
        yield db
    # 重置 style_service 缓存，避免泄漏到其他测试
    style_service._cache.clear()
    style_service._loaded = False
    await engine.dispose()


@pytest.fixture
def developer():
    return User(id=1, username="dev", hashed_password="x", is_developer=True)


@pytest.fixture
async def seeded_styles(db_session):
    """插入与 style_service.STYLES 一致的内置风格种子。"""
    rows = [
        ImageStyle(
            style_id=s["id"], label=s["label"], style_prompt=s["style_prompt"],
            analysis_hint=s["analysis_hint"], sort_order=i, is_active=True, is_system=True,
        )
        for i, s in enumerate(style_service.STYLES)
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return rows


# ── style_service DB 驱动 ──

class TestStyleServiceDB:
    @pytest.mark.asyncio
    async def test_load_cache_loads_active_styles(self, db_session, seeded_styles):
        await style_service.load_cache(db_session)
        assert style_service._loaded is True
        assert len(style_service._cache) == len(seeded_styles)
        assert "pixel_16bit" in style_service._cache
        # DB 数据与硬编码一致
        assert style_service.get_style_prompt("watercolor") == style_service._STYLE_MAP["watercolor"]["style_prompt"]

    @pytest.mark.asyncio
    async def test_load_cache_skips_inactive(self, db_session, seeded_styles):
        ink = await db_session.scalar(select(ImageStyle).where(ImageStyle.style_id == "ink_wash"))
        ink.is_active = False
        await db_session.commit()
        await style_service.load_cache(db_session)
        assert "ink_wash" not in style_service._cache
        assert len(style_service._cache) == len(seeded_styles) - 1

    @pytest.mark.asyncio
    async def test_get_style_falls_back_to_default_for_unknown(self, db_session, seeded_styles):
        await style_service.load_cache(db_session)
        assert style_service.get_style("nonexistent")["id"] == style_service.DEFAULT_STYLE_ID
        assert style_service.get_style(None)["id"] == style_service.DEFAULT_STYLE_ID

    @pytest.mark.asyncio
    async def test_list_styles_uses_cache_after_load(self, db_session, seeded_styles):
        await style_service.load_cache(db_session)
        styles = style_service.list_styles()
        # 按 sort_order 升序，与 STYLES 原始顺序一致
        assert [s["id"] for s in styles] == [s["id"] for s in style_service.STYLES]
        for s in styles:
            assert "style_prompt" not in s  # 不暴露细节

    @pytest.mark.asyncio
    async def test_reload_cache_picks_up_new_style(self, db_session, seeded_styles):
        await style_service.load_cache(db_session)
        assert "cyberpunk" not in style_service._cache
        db_session.add(ImageStyle(
            style_id="cyberpunk", label="赛博朋克", style_prompt="neon",
            analysis_hint="CYBERPUNK", sort_order=99, is_active=True, is_system=False,
        ))
        await db_session.commit()
        await style_service.reload_cache()
        assert "cyberpunk" in style_service._cache


# ── admin 风格 CRUD ──

class TestAdminStyleCRUD:
    @pytest.mark.asyncio
    async def test_list_returns_all_fields(self, db_session, seeded_styles, developer):
        result = await admin.list_styles(developer)
        assert result["ok"] is True
        assert len(result["data"]) == len(seeded_styles)
        first = result["data"][0]
        assert first["styleId"] == "pixel_16bit"
        assert "stylePrompt" in first and "isSystem" in first and "isActive" in first

    @pytest.mark.asyncio
    async def test_create_style_and_refresh_cache(self, db_session, developer):
        body = admin.StyleCreateReq(
            style_id="cyberpunk", label="赛博朋克",
            style_prompt="cyberpunk neon", analysis_hint="CYBERPUNK", sort_order=10,
        )
        result = await admin.create_style(body, developer)
        assert result["ok"] is True
        assert result["data"]["styleId"] == "cyberpunk"
        assert result["data"]["isSystem"] is False
        # 缓存已刷新
        assert style_service._loaded is True
        assert "cyberpunk" in style_service._cache

    @pytest.mark.asyncio
    async def test_create_rejects_duplicate(self, db_session, seeded_styles, developer):
        body = admin.StyleCreateReq(style_id="pixel_16bit", label="重复", style_prompt="x")
        with pytest.raises(HTTPException) as exc:
            await admin.create_style(body, developer)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_update_style_and_refresh_cache(self, db_session, seeded_styles, developer):
        body = admin.StyleUpdateReq(label="新像素风", is_active=False)
        result = await admin.update_style("pixel_16bit", body, developer)
        assert result["data"]["label"] == "新像素风"
        assert result["data"]["isActive"] is False
        # 下架后缓存刷新，pixel_16bit 不再出现在 active 缓存
        assert "pixel_16bit" not in style_service._cache

    @pytest.mark.asyncio
    async def test_update_not_found(self, db_session, developer):
        with pytest.raises(HTTPException) as exc:
            await admin.update_style("nonexistent", admin.StyleUpdateReq(label="x"), developer)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_custom_style(self, db_session, developer):
        body = admin.StyleCreateReq(style_id="temp", label="临时", style_prompt="x")
        await admin.create_style(body, developer)
        result = await admin.delete_style("temp", developer)
        assert result["ok"] is True
        assert "temp" not in style_service._cache

    @pytest.mark.asyncio
    async def test_delete_system_style_rejected(self, db_session, seeded_styles, developer):
        with pytest.raises(HTTPException) as exc:
            await admin.delete_style("pixel_16bit", developer)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db_session, developer):
        with pytest.raises(HTTPException) as exc:
            await admin.delete_style("nonexistent", developer)
        assert exc.value.status_code == 404
