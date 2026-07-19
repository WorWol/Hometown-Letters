"""本地监控数据维护：清理过期结构化事件。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from config import settings
from db.database import async_session
from db.models import SystemEvent


async def cleanup_old_events() -> int:
    """删除超过保留期限的事件，返回删除数量。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(settings.event_retention_days, 1))
    async with async_session() as db:
        result = await db.execute(delete(SystemEvent).where(SystemEvent.created_at < cutoff))
        await db.commit()
        return result.rowcount or 0
