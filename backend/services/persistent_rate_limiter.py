"""SQLite-backed authentication rate limiter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text

from db.database import async_session
from db.models import RateLimitEvent


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    retry_after: int = 0


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def hit_many(checks: tuple[tuple[str, int, int], ...]) -> LimitResult:
    """在一个 SQLite IMMEDIATE 事务内检查并写入全部限流桶，避免并发穿透。"""
    if not checks:
        return LimitResult(True)
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        await db.execute(text("BEGIN IMMEDIATE"))
        try:
            for key, limit, window_seconds in checks:
                cutoff = now - timedelta(seconds=window_seconds)
                await db.execute(delete(RateLimitEvent).where(RateLimitEvent.key == key, RateLimitEvent.created_at < cutoff))
                count = await db.scalar(select(func.count(RateLimitEvent.id)).where(RateLimitEvent.key == key)) or 0
                if count >= limit:
                    oldest = await db.scalar(select(func.min(RateLimitEvent.created_at)).where(RateLimitEvent.key == key))
                    await db.rollback()
                    retry = max(1, int((_utc(oldest) + timedelta(seconds=window_seconds) - now).total_seconds() + 0.999)) if oldest else window_seconds
                    return LimitResult(False, retry)
            for key, _, _ in checks:
                db.add(RateLimitEvent(key=key, created_at=now))
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return LimitResult(True)


async def hit(key: str, limit: int, window_seconds: int) -> LimitResult:
    """单桶调用入口，复用原子批量事务。"""
    return await hit_many(((key, limit, window_seconds),))


async def clear(*keys: str) -> None:
    if not keys:
        return
    async with async_session() as db:
        await db.execute(delete(RateLimitEvent).where(RateLimitEvent.key.in_(keys)))
        await db.commit()


async def check_registration(ip: str, username: str) -> LimitResult:
    return await hit_many((
        (f"register:ip:hour:{ip}", 3, 3600),
        (f"register:ip:day:{ip}", 5, 86400),
        (f"register:user:{username.casefold()}", 5, 900),
    ))


async def check_login_failure(ip: str, username: str) -> LimitResult:
    return await hit_many((
        (f"login:ip:{ip}", 10, 900),
        (f"login:user:{username.casefold()}", 5, 900),
    ))


async def clear_login_failures(ip: str, username: str) -> None:
    await clear(f"login:ip:{ip}", f"login:user:{username.casefold()}")
