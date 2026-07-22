"""开发者后台认证、健康检查和存储任务测试。"""
from __future__ import annotations

import pytest
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin import _oss_key_status, health, storage_check
from admin_data import _payload
from auth.developer import get_current_developer, require_current_developer
from auth.security import create_token
from app.factory import create_app
from db.models import Base, Postcard, User
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


@pytest.fixture
async def database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        await connection.execute(text("INSERT INTO alembic_version(version_num) VALUES ('test')"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("admin.async_session", maker)
    async with maker() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_developer_dependency_accepts_developer_and_rejects_regular_user(database):
    developer = User(username="developer", hashed_password="x", is_developer=True)
    regular = User(username="regular", hashed_password="x", is_developer=False)
    database.add_all([developer, regular])
    await database.commit()

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_token(developer.id, developer.username, is_developer=True))
    # Use fresh sessions because the dependency owns the session lifecycle in production.
    maker = async_sessionmaker(database.bind, class_=AsyncSession, expire_on_commit=False)
    developer_session = maker()
    try:
        assert (await get_current_developer(credentials, developer_session)).id == developer.id
    finally:
        await developer_session.close()

    regular_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_token(regular.id, regular.username))
    regular_session = maker()
    try:
        assert await get_current_developer(regular_credentials, regular_session) is None
    finally:
        await regular_session.close()

    empty_session = maker()
    try:
        with pytest.raises(HTTPException) as error:
            await require_current_developer(None, empty_session)
        assert error.value.status_code == 401
    finally:
        await empty_session.close()


@pytest.mark.asyncio
async def test_health_checks_database_migration_and_storage(database, monkeypatch):
    monkeypatch.setattr("admin.storage.validate_config", lambda: None)
    result = await health()
    assert result["ok"] is True
    assert result["data"]["migration"] == "test"
    assert result["data"]["storage"] == "configured"


def test_postcard_limit_is_editable_but_developer_role_is_not():
    values = _payload("users", {"postcard_limit": 20}, creating=False)
    assert values == {"postcard_limit": 20}
    with pytest.raises(HTTPException):
        _payload("users", {"is_developer": True}, creating=False)


@pytest.mark.asyncio
async def test_frontend_entrypoints_do_not_keep_stale_code_cached():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        html = await client.get("/admin/admin.html")
        javascript = await client.get("/admin/admin.js?v=test")

    assert html.status_code == 200
    assert html.headers["cache-control"] == "no-store"
    assert javascript.status_code == 200
    assert javascript.headers["cache-control"] == "public, max-age=0, must-revalidate"


@pytest.mark.asyncio
async def test_user_frontend_uses_same_origin_api_in_production():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/")
        api_script = await client.get("/js/core/api.js?v=test")

    assert page.status_code == 200
    assert "js/core/api.js" in page.text
    assert api_script.status_code == 200
    assert "http://127.0.0.1:8787" not in api_script.text
    assert "const API_BASE = isLocalFrontendServer" in api_script.text


@pytest.mark.asyncio
async def test_oss_key_status_returns_none_on_network_failure(monkeypatch):
    """单个对象 OSS 请求失败应返回 None，不击垮整批一致性检查。"""
    async def fake_exists(key):
        if not key:
            return False
        if key == "fail":
            raise ConnectionError("SSL EOF")
        return True

    monkeypatch.setattr("admin.storage.object_exists_async", fake_exists)
    present = await _oss_key_status({"ok": "k1", "broken": "fail", "empty": ""})
    assert present == {"ok": True, "broken": None, "empty": False}


@pytest.mark.asyncio
async def test_storage_check_reports_three_state_consistency(database, monkeypatch):
    """complete 三态：无图=None，全存在=True，有缺失=False，含检查失败=None。"""
    database.add_all([
        User(id=1, username="dev", hashed_password="x", is_developer=True),
        Postcard(id=1, user_id=1),  # 无图：keys 全空
        Postcard(id=2, user_id=1, image_thumb_key="k/B/thumb", image_card_key="k/B/card",
                 image_original_key="k/B/original", reference_image_key="k/B/reference"),  # 全存在
        Postcard(id=3, user_id=1, image_thumb_key="k/C/thumb", image_card_key="k/C/card",
                 image_original_key="k/C/original", reference_image_key="k/C/reference"),  # thumb 缺失
        Postcard(id=4, user_id=1, image_thumb_key="k/D/thumb", image_card_key="k/D/card",
                 image_original_key="k/D/original", reference_image_key="k/D/reference"),  # original 检查失败
    ])
    await database.commit()

    async def fake_exists(key):
        if "/C/thumb" in key:
            return False
        if "/D/original" in key:
            raise ConnectionError("SSL EOF")
        return bool(key)

    monkeypatch.setattr("admin.storage.object_exists_async", fake_exists)
    result = await storage_check(postcard_id=None, developer=None)
    items = {item["postcardId"]: item for item in result["data"]["items"]}

    assert result["data"]["checked"] == 4
    assert items[1]["complete"] is None  # 无图：中性，不再误报「需处理」
    assert items[2]["complete"] is True  # 全部存在
    assert items[3]["complete"] is False  # 有缺失
    assert items[4]["complete"] is None  # 含检查失败：无法判定
    assert items[4]["present"]["original"] is None
    assert items[4]["present"]["thumb"] is True
