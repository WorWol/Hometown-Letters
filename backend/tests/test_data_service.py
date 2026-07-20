"""统一删除服务和派生计数回归测试。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base, Mail, Postcard, StorageDeletionTask, User
from services import data_service


@pytest.fixture
async def database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async def no_delete(_keys):
        return None
    monkeypatch.setattr(data_service.storage, "delete_images", no_delete)
    async with maker() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_postcard_clears_mail_and_updates_count(database):
    user = User(username="delete-test", hashed_password="x", postcard_count=1)
    database.add(user)
    await database.flush()
    postcard = Postcard(user_id=user.id, image_thumb_key="a", image_card_key="b", image_original_key="c", created_at=datetime.now(timezone.utc))
    database.add(postcard)
    await database.flush()
    database.add(Mail(sender_id=user.id, recipient_id=user.id, content="x", attached_postcard_id=postcard.id))
    await database.flush()
    await data_service.delete_postcard(database, postcard)
    await database.commit()
    assert await database.scalar(select(Postcard.id).where(Postcard.id == postcard.id)) is None
    assert await database.scalar(select(User.postcard_count).where(User.id == user.id)) == 0
    assert await database.scalar(select(Mail.attached_postcard_id).where(Mail.sender_id == user.id)) is None


@pytest.mark.asyncio
async def test_recalculate_postcard_count(database):
    user = User(username="count-test", hashed_password="x", postcard_count=99)
    database.add(user)
    await database.flush()
    database.add_all([
        Postcard(user_id=user.id, image_thumb_key="a", image_card_key="b", image_original_key="c"),
        Postcard(user_id=user.id, image_thumb_key="d", image_card_key="e", image_original_key="f"),
    ])
    await database.flush()
    count = await data_service.recalculate_postcard_count(database, user.id)
    await database.commit()
    assert count == 2
    assert await database.scalar(select(User.postcard_count).where(User.id == user.id)) == 2


@pytest.mark.asyncio
async def test_delete_postcard_records_storage_retry_and_removes_database_row(database, monkeypatch):
    user = User(username="storage-failure", hashed_password="x", postcard_count=1)
    database.add(user)
    await database.flush()
    postcard = Postcard(
        user_id=user.id,
        image_thumb_key="failed-thumb",
        image_card_key="failed-card",
        image_original_key="failed-original",
    )
    database.add(postcard)
    await database.flush()

    async def fail_delete(_keys):
        raise RuntimeError("oss unavailable")

    monkeypatch.setattr(data_service.storage, "delete_images", fail_delete)
    await data_service.delete_postcard(database, postcard)
    await database.commit()

    assert await database.scalar(select(Postcard.id).where(Postcard.id == postcard.id)) is None
    task = await database.scalar(select(StorageDeletionTask))
    assert task is not None
    assert task.status == "pending"
    assert task.entity_type == "postcard"
    assert task.last_error == "oss unavailable"
    assert task.object_keys["reference"] == ""
