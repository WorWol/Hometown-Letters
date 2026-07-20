"""OSS 删除失败任务的记录与重试。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import storage
from db.database import async_session
from db.models import StorageDeletionTask


async def add_task(db: AsyncSession, entity_type: str, entity_id: int, object_keys: dict[str, str], error: Exception) -> None:
    """把清理任务加入当前事务，确保业务删除和任务记录一起提交。"""
    db.add(StorageDeletionTask(
        entity_type=entity_type,
        entity_id=entity_id,
        object_keys=object_keys,
        status="pending",
        last_error=str(error)[:1000],
    ))
    await db.flush()


async def retry_pending(limit: int = 20) -> int:
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        tasks = (await db.scalars(
            select(StorageDeletionTask)
            .where(StorageDeletionTask.status == "pending")
            .order_by(StorageDeletionTask.updated_at)
            .limit(limit)
        )).all()
        completed = 0
        for task in tasks:
            try:
                await storage.delete_images(task.object_keys)
                task.status = "completed"
                task.last_error = None
                completed += 1
            except Exception as error:
                task.attempts += 1
                task.last_error = str(error)[:1000]
                if task.attempts >= 10:
                    task.status = "failed"
            task.updated_at = now
        await db.commit()
    return completed
