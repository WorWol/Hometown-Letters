"""持久化限流和指标的最小回归测试。"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import ApiMetric, Base
from services import persistent_metrics, persistent_rate_limiter


@pytest.fixture
async def database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(persistent_metrics, "async_session", maker)
    monkeypatch.setattr(persistent_rate_limiter, "async_session", maker)
    async with maker() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_rate_limit_persists_in_database(database):
    key = "test:ip"
    assert (await persistent_rate_limiter.hit(key, 1, 3600)).allowed
    blocked = await persistent_rate_limiter.hit(key, 1, 3600)
    assert not blocked.allowed
    await persistent_rate_limiter.clear(key)
    assert (await persistent_rate_limiter.hit(key, 1, 3600)).allowed


@pytest.mark.asyncio
async def test_api_metrics_snapshot_is_database_backed(database):
    await persistent_metrics.record("GET", "/api/postcards/123", 200, 12.4)
    await persistent_metrics.record("GET", "/api/postcards/456", 500, 20.1)
    snapshot = await persistent_metrics.snapshot()
    assert snapshot["total"]["count"] == 2
    assert snapshot["total"]["serverErrors"] == 1
    assert snapshot["routes"][0]["path"] == "/api/postcards/<id>"


@pytest.mark.asyncio
async def test_api_metrics_write_is_deferred_until_flush(database):
    path = "/api/deferred-metric"
    await persistent_metrics.record("GET", path, 200, 5)
    async with persistent_metrics.async_session() as db:
        assert await db.scalar(select(ApiMetric).where(ApiMetric.path == path)) is None
    await persistent_metrics.flush()
    async with persistent_metrics.async_session() as db:
        row = await db.scalar(select(ApiMetric).where(ApiMetric.path == path))
        assert row is not None
        assert row.count == 1
