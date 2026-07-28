"""用户明信片画风偏好的持久化测试。"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.routers import profile as profile_router
from db.models import Base, Profile, User
from services import style_service


@pytest.fixture
async def session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(style_service, "_loaded", False)
    monkeypatch.setattr(style_service, "_cache", {})
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_image_style_persists_for_existing_profile(session_factory):
    async with session_factory() as db:
        user = User(username="style-user", hashed_password="x")
        db.add(user)
        await db.flush()
        db.add(Profile(user_id=user.id, data={"kept": "value"}))
        await db.commit()

        response = await profile_router.set_image_style(
            profile_router.ImageStyleReq(style_id="watercolor"),
            user,
            db,
        )
        assert response == {"ok": True, "data": {"imageStyle": "watercolor"}}
        await db.commit()
        user_id = user.id

    async with session_factory() as db:
        saved = await db.scalar(select(Profile).where(Profile.user_id == user_id))
        assert saved is not None
        assert saved.data == {"kept": "value", "image_style": "watercolor"}
