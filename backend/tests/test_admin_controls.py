"""开发者后台认证、健康检查和存储任务测试。"""
from __future__ import annotations

import pytest
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin import health
from admin_data import _payload
from auth.developer import get_current_developer, require_current_developer
from auth.security import create_token
from app.factory import create_app
from db.models import Base, User
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
        html = await client.get("/admin.html")
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
