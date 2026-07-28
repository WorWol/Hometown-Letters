"""新人引导账户状态的持久化回归测试。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.routers import profile as profile_router
from auth import routes as auth_routes
from db.models import Base, Profile, User


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_onboarding_version_preserves_existing_profile_data(session_factory):
    async with session_factory() as db:
        user = User(username="onboarding-user", hashed_password="x")
        db.add(user)
        await db.flush()
        db.add(Profile(user_id=user.id, data={"image_style": "watercolor"}))
        await db.commit()

        response = await profile_router.set_onboarding_version(
            profile_router.OnboardingReq(version=1),
            user,
            db,
        )
        assert response == {"ok": True, "data": {"onboardingVersion": 1}}
        await db.commit()
        user_id = user.id

    async with session_factory() as db:
        saved = await db.scalar(select(Profile).where(Profile.user_id == user_id))
        assert saved is not None
        assert saved.data == {
            "image_style": "watercolor",
            "onboarding_version": 1,
        }


@pytest.mark.asyncio
async def test_registration_marks_new_user_for_onboarding(session_factory, monkeypatch):
    async def allow_registration(*_args, **_kwargs):
        return SimpleNamespace(allowed=True, retry_after=0)

    monkeypatch.setattr(auth_routes, "check_registration", allow_registration)
    monkeypatch.setattr(auth_routes, "create_token", lambda *_args, **_kwargs: "test-token")
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/register",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    })

    async with session_factory() as db:
        response = await auth_routes.register(
            request,
            auth_routes.AuthRequest(username="new-guide-user", password="secret"),
            db,
        )
        assert response["ok"] is True
        await db.commit()
        user = await db.scalar(select(User).where(User.username == "new-guide-user"))
        profile = await db.scalar(select(Profile).where(Profile.user_id == user.id))
        assert profile is not None
        assert profile.data == {"onboarding_version": 0}
