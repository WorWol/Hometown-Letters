"""API 指标采集与批量持久化。"""
from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from db.database import async_session
from db.models import ApiMetric

_ID_SEGMENT = re.compile(r"^(?:\d+|[0-9a-f]{8,})$", re.IGNORECASE)


@dataclass
class _Pending:
    count: int = 0
    success: int = 0
    client_errors: int = 0
    server_errors: int = 0
    total_ms: int = 0
    max_ms: int = 0
    last_status: int = 0
    last_at: datetime | None = None


_lock = threading.Lock()
_pending: dict[tuple[str, str], _Pending] = {}
_flush_lock = asyncio.Lock()


def normalize_path(path: str) -> str:
    return "/".join("<id>" if _ID_SEGMENT.match(part) else part for part in path.split("/")) or "/"


def _serialize(row: _Pending | ApiMetric) -> dict:
    return {
        "method": row.method if isinstance(row, ApiMetric) else "",
        "path": row.path if isinstance(row, ApiMetric) else "",
        "count": row.count,
        "success": row.success,
        "clientErrors": row.client_errors,
        "serverErrors": row.server_errors,
        "averageMs": round(row.total_ms / row.count, 2) if row.count else 0,
        "maxMs": row.max_ms,
        "lastStatus": row.last_status,
        "lastAt": row.last_at.timestamp() if row.last_at else 0,
    }


async def record(method: str, path: str, status_code: int, elapsed_ms: float) -> None:
    """只更新进程内聚合计数，不在请求链路写 SQLite。"""
    key = (method.upper(), normalize_path(path))
    value = max(0, int(round(elapsed_ms)))
    with _lock:
        metric = _pending.setdefault(key, _Pending())
        metric.count += 1
        metric.success += int(200 <= status_code < 400)
        metric.client_errors += int(400 <= status_code < 500)
        metric.server_errors += int(status_code >= 500)
        metric.total_ms += value
        metric.max_ms = max(metric.max_ms, value)
        metric.last_status = status_code
        metric.last_at = datetime.now(timezone.utc)


async def flush() -> None:
    """将当前批次一次性写入 SQLite。"""
    async with _flush_lock:
        with _lock:
            batch = _pending.copy()
            _pending.clear()
        if not batch:
            return
        async with async_session() as db:
            for (method, path), pending in batch.items():
                row = await db.scalar(select(ApiMetric).where(ApiMetric.method == method, ApiMetric.path == path))
                if row is None:
                    row = ApiMetric(method=method, path=path, count=0, success=0, client_errors=0, server_errors=0, total_ms=0, max_ms=0, last_status=0)
                    db.add(row)
                row.count += pending.count
                row.success += pending.success
                row.client_errors += pending.client_errors
                row.server_errors += pending.server_errors
                row.total_ms += pending.total_ms
                row.max_ms = max(row.max_ms, pending.max_ms)
                row.last_status = pending.last_status
                row.last_at = pending.last_at
            await db.commit()


async def snapshot(limit: int = 100) -> dict:
    await flush()
    async with async_session() as db:
        rows = (await db.scalars(select(ApiMetric).order_by(ApiMetric.count.desc(), ApiMetric.last_at.desc()).limit(limit))).all()
        all_rows = (await db.scalars(select(ApiMetric))).all()
    total = _Pending()
    for row in all_rows:
        total.count += row.count
        total.success += row.success
        total.client_errors += row.client_errors
        total.server_errors += row.server_errors
        total.total_ms += row.total_ms
        total.max_ms = max(total.max_ms, row.max_ms)
        total.last_status = row.last_status
        total.last_at = row.last_at
    total_data = _serialize(total)
    total_data.update(method="", path="")
    return {"total": total_data, "routes": [{**_serialize(row), "method": row.method, "path": row.path} for row in rows]}
