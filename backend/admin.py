"""开发者后台 API。所有接口统一使用开发者账号 Bearer Token。"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from config import settings
from db.database import async_session
from db.models import ImageStyle, Letter, Postcard, StorageDeletionTask, SystemEvent, User
from logger import LOG_FILE
import storage
from services import persistent_metrics
from services.runtime_metrics import snapshot as runtime_snapshot
from services.data_service import delete_postcard as remove_postcard
from auth.developer import require_current_developer
from services import prompt_service

router = APIRouter(prefix="/api/admin", tags=["admin"])
_started_at = time.time()
logger = logging.getLogger("hometown")
# OSS 一致性检查的并发上限：单张明信片内 4 个对象并发，再以此额度并发多张明信片。
# 兼顾速度与避免压垮 OSS 触发 SSL 重置（实测并发 15 次单 key 稳定）。
_OSS_CHECK_CONCURRENCY = 6


def _read_log_tail(path: Path, limit: int) -> list[str]:
    """从文件尾部读取有限行，避免后台请求把整个日志文件读入内存。"""
    lines: list[str] = []
    with path.open("rb") as file:
        file.seek(0, 2)
        buffer = b""
        while file.tell() > 0 and len(lines) <= limit:
            read_size = min(8192, file.tell())
            file.seek(-read_size, 1)
            buffer = file.read(read_size) + buffer
            file.seek(-read_size, 1)
            lines = buffer.decode("utf-8", errors="replace").splitlines()
    return lines[-limit:]


class PostcardPatch(BaseModel):
    """开发者允许修改的明信片字段白名单。"""

    title: str | None = Field(default=None, max_length=256)
    body: str | None = None
    poem: str | None = None
    place: str | None = Field(default=None, max_length=128)
    mood: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = None
    imagePrompt: str | None = None
    letterText: str | None = None

class PromptUpdateReq(BaseModel):
    """开发者修改提示词时的请求体。"""
    content: str = Field(max_length=20000)


def _postcard_dict(row: Postcard) -> dict:
    return {
        "id": row.id,
        "userId": row.user_id,
        "title": row.title,
        "body": row.body,
        "poem": row.poem,
        "place": row.place,
        "generationPlace": row.generation_place,
        "mood": row.mood,
        "tags": row.tags or [],
        "imagePrompt": row.image_prompt,
        "letterText": row.letter_text,
        "createdAt": row.created_at.isoformat() if row.created_at else "",
        "imageKeys": {
            "thumb": row.image_thumb_key,
            "card": row.image_card_key,
            "original": row.image_original_key,
            "reference": row.reference_image_key,
        },
    }


def _postcard_image_urls(row: Postcard) -> dict[str, str]:
    return {
        "thumb": storage.image_url(row.image_thumb_key),
        "card": storage.image_url(row.image_card_key),
        "original": storage.image_url(row.image_original_key),
        "reference": storage.image_url(row.reference_image_key),
    }


async def _oss_key_status(keys: dict[str, str]) -> dict[str, bool | None]:
    """检查明信片图片对象是否存在于 OSS；请求放到线程避免阻塞事件循环。

    返回值三态：True 存在 / False 不存在 / None 检查失败（网络异常等）。
    单个对象检查失败只影响该对象，不会让整张明信片或整个请求失败。
    """
    async def check(name: str, key: str) -> tuple[str, bool | None]:
        if not key:
            return name, False
        try:
            return name, await storage.object_exists_async(key)
        except Exception as exc:  # OSS 网络抖动（如 SSL EOF）不应击垮整个一致性检查
            logger.warning("OSS object_exists failed for %s: %r", key, exc)
            return name, None

    pairs = await asyncio.gather(*(check(name, key) for name, key in keys.items()))
    return dict(pairs)


@router.get("/overview")
async def overview(developer: User = Depends(require_current_developer)):
    async with async_session() as db:
        users = await db.scalar(select(func.count(User.id))) or 0
        letters = await db.scalar(select(func.count(Letter.id))) or 0
        postcards = await db.scalar(select(func.count(Postcard.id))) or 0
        recent_errors = await db.scalar(
            select(func.count(SystemEvent.id)).where(
                SystemEvent.level.in_(["error", "critical"]),
                SystemEvent.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
            )
        ) or 0

    disk = shutil.disk_usage("/")
    return {
        "ok": True,
        "data": {
            "environment": settings.environment,
            "uptimeSeconds": int(time.time() - _started_at),
            "users": users,
            "letters": letters,
            "postcards": postcards,
            "errorsToday": recent_errors,
            "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
            "storageBackend": settings.storage_backend,
            "apiMetrics": await persistent_metrics.snapshot(limit=10),
            "runtime": runtime_snapshot(),
        },
    }


@router.get("/metrics")
async def metrics(developer: User = Depends(require_current_developer)):
    return {"ok": True, "data": await persistent_metrics.snapshot(limit=200)}


@router.get("/runtime")
async def runtime(developer: User = Depends(require_current_developer)):
    return {"ok": True, "data": runtime_snapshot()}


@router.get("/users")
async def users(
    q: str = Query(default="", max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    developer: User = Depends(require_current_developer),
):
    async with async_session() as db:
        query = select(User).order_by(User.id.desc()).limit(limit)
        if q.strip():
            query = query.where(User.username.contains(q.strip()))
        rows = (await db.execute(query)).scalars().all()
    return {
        "ok": True,
        "data": [
            {
                "id": row.id,
                "username": row.username,
                "currentDay": row.current_day,
                "postcardCount": row.postcard_count,
                "postcardLimit": row.postcard_limit,
            }
            for row in rows
        ],
    }


@router.get("/postcards")
async def postcards(
    q: str = Query(default="", max_length=128),
    user_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    developer: User = Depends(require_current_developer),
):
    async with async_session() as db:
        query = select(Postcard).order_by(Postcard.created_at.desc()).offset(offset).limit(limit)
        if user_id is not None:
            query = query.where(Postcard.user_id == user_id)
        if q.strip():
            term = q.strip()
            query = query.where(
                Postcard.title.contains(term)
                | Postcard.place.contains(term)
                | Postcard.body.contains(term)
            )
        rows = (await db.execute(query)).scalars().all()
        total_query = select(func.count(Postcard.id))
        if user_id is not None:
            total_query = total_query.where(Postcard.user_id == user_id)
        if q.strip():
            term = q.strip()
            total_query = total_query.where(
                Postcard.title.contains(term)
                | Postcard.place.contains(term)
                | Postcard.body.contains(term)
            )
        total = await db.scalar(total_query) or 0
        data = []
        for row in rows:
            item = _postcard_dict(row)
            item["ossStatus"] = await _oss_key_status(item["imageKeys"])
            data.append(item)
    return {"ok": True, "data": {"items": data, "total": total, "offset": offset, "limit": limit}}


@router.get("/postcards/{postcard_id}")
async def postcard_detail(postcard_id: int, developer: User = Depends(require_current_developer)):
    async with async_session() as db:
        row = await db.scalar(select(Postcard).where(Postcard.id == postcard_id))
        if row is None:
            raise HTTPException(status_code=404, detail="明信片不存在")
        data = _postcard_dict(row)
        data["imageUrls"] = _postcard_image_urls(row)
        data["ossStatus"] = await _oss_key_status(data["imageKeys"])
    return {"ok": True, "data": data}


@router.patch("/postcards/{postcard_id}")
async def update_postcard(
    postcard_id: int,
    body: PostcardPatch,
    developer: User = Depends(require_current_developer),
):
    changes = body.model_dump(exclude_unset=True)
    field_map = {"imagePrompt": "image_prompt", "letterText": "letter_text"}
    changes = {field_map.get(key, key): value for key, value in changes.items()}
    async with async_session() as db:
        row = await db.scalar(select(Postcard).where(Postcard.id == postcard_id))
        if row is None:
            raise HTTPException(status_code=404, detail="明信片不存在")
        before = _postcard_dict(row)
        for key, value in changes.items():
            setattr(row, key, value)
        await db.flush()
        db.add(SystemEvent(
            level="info",
            event_type="admin_postcard_updated",
            message="developer updated postcard fields",
            event_metadata={"actor": developer.username, "postcardId": postcard_id, "fields": list(changes), "before": before},
        ))
        await db.commit()
        data = _postcard_dict(row)
    return {"ok": True, "data": data}


@router.delete("/postcards/{postcard_id}")
async def delete_postcard(
    postcard_id: int,
    developer: User = Depends(require_current_developer),
):
    async with async_session() as db:
        row = await db.scalar(select(Postcard).where(Postcard.id == postcard_id))
        if row is None:
            raise HTTPException(status_code=404, detail="明信片不存在")
        # OSS 失败会进入清理任务，但数据库删除继续提交，避免后台操作长期卡住。
        await remove_postcard(db, row)
        before = _postcard_dict(row)
        db.add(SystemEvent(
            level="warning",
            event_type="admin_postcard_deleted",
            message="developer deleted postcard and OSS objects",
            event_metadata={"actor": developer.username, "postcardId": postcard_id, "before": before},
        ))
        await db.commit()
    return {"ok": True, "data": {"id": postcard_id}}


@router.get("/storage/check")
async def storage_check(
    postcard_id: int | None = Query(default=None, ge=1),
    developer: User = Depends(require_current_developer),
):
    async with async_session() as db:
        query = select(Postcard).order_by(Postcard.id)
        if postcard_id is not None:
            query = query.where(Postcard.id == postcard_id)
        rows = list((await db.execute(query)).scalars().all())

    semaphore = asyncio.Semaphore(_OSS_CHECK_CONCURRENCY)

    async def inspect(row: Postcard) -> dict:
        keys = {
            "thumb": row.image_thumb_key,
            "card": row.image_card_key,
            "original": row.image_original_key,
            "reference": row.reference_image_key,
        }
        async with semaphore:
            present = await _oss_key_status(keys)
        tracked = [name for name, key in keys.items() if key]
        # complete 三态：True 全部存在 / False 有缺失 / None 无图或含检查失败（无法判定）
        if not tracked:
            complete = None
        elif any(present[name] is None for name in tracked):
            complete = None
        else:
            complete = all(present[name] for name in tracked)
        return {
            "postcardId": row.id,
            "keys": keys,
            "present": present,
            "complete": complete,
        }

    items = list(await asyncio.gather(*(inspect(row) for row in rows)))
    return {"ok": True, "data": {"items": items, "checked": len(items)}}


@router.get("/storage/tasks")
async def storage_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    developer: User = Depends(require_current_developer),
):
    async with async_session() as db:
        query = select(StorageDeletionTask).order_by(StorageDeletionTask.updated_at.asc()).limit(limit)
        if status_filter:
            query = query.where(StorageDeletionTask.status == status_filter)
        rows = (await db.scalars(query)).all()
    return {"ok": True, "data": [
        {
            "id": row.id,
            "entityType": row.entity_type,
            "entityId": row.entity_id,
            "objectKeys": row.object_keys,
            "status": row.status,
            "attempts": row.attempts,
            "lastError": row.last_error,
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
        }
        for row in rows
    ]}


@router.post("/storage/tasks/retry")
async def retry_storage_tasks(developer: User = Depends(require_current_developer)):
    from services.storage_tasks import retry_pending
    completed = await retry_pending()
    return {"ok": True, "data": {"completed": completed}}


@router.get("/events")
async def events(
    limit: int = Query(default=100, ge=1, le=500),
    level: str | None = Query(default=None),
    developer: User = Depends(require_current_developer),
):
    async with async_session() as db:
        query = select(SystemEvent).order_by(SystemEvent.created_at.desc()).limit(limit)
        if level:
            query = query.where(SystemEvent.level == level)
        rows = (await db.execute(query)).scalars().all()
    return {
        "ok": True,
        "data": [
            {
                "id": row.id,
                "level": row.level,
                "eventType": row.event_type,
                "message": row.message,
                "userId": row.user_id,
                "requestId": row.request_id,
                "metadata": row.event_metadata or {},
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/logs")
async def logs(
    limit: int = Query(default=200, ge=1, le=1000),
    developer: User = Depends(require_current_developer),
):
    """读取本地应用日志的末尾内容，不上传 OSS，也不暴露任意文件路径。"""
    log_file = Path(LOG_FILE)
    if not log_file.exists():
        return {"ok": True, "data": {"path": str(log_file), "lines": []}}
    return {
        "ok": True,
        "data": {
            "path": str(log_file),
            "lines": _read_log_tail(log_file, min(limit, settings.admin_log_lines)),
        },
    }


@router.get("/health")
async def health():
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            migration = await db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        storage.validate_config()
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"服务健康检查失败: {error}") from error
    return {"ok": True, "data": {
        "status": "ok",
        "migration": migration,
        "storage": "configured",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }}


# ── 提示词管理 ──

@router.get("/prompts")
async def list_prompts(developer: User = Depends(require_current_developer)):
    return {"ok": True, "data": await prompt_service.list_prompts()}


@router.put("/prompts/{key}")
async def update_prompt(
    key: str,
    body: PromptUpdateReq,
    developer: User = Depends(require_current_developer),
):
    try:
        await prompt_service.set_override(key, body.content, developer.username)
    except KeyError:
        raise HTTPException(status_code=404, detail="未知提示词")
    async with async_session() as db:
        db.add(SystemEvent(
            level="info",
            event_type="admin_prompt_updated",
            message="developer updated LLM prompt",
            event_metadata={"actor": developer.username, "key": key},
        ))
        await db.commit()
    return {"ok": True, "data": {"key": key, "overridden": True}}


@router.delete("/prompts/{key}")
async def reset_prompt(
    key: str,
    developer: User = Depends(require_current_developer),
):
    try:
        await prompt_service.reset_override(key)
    except KeyError:
        raise HTTPException(status_code=404, detail="未知提示词")
    async with async_session() as db:
        db.add(SystemEvent(
            level="info",
            event_type="admin_prompt_reset",
            message="developer reset LLM prompt to default",
            event_metadata={"actor": developer.username, "key": key},
        ))
        await db.commit()
    return {"ok": True, "data": {"key": key, "overridden": False}}


# ── 图像风格管理 ──

class StyleCreateReq(BaseModel):
    style_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=64)
    style_prompt: str = Field(max_length=2000)
    analysis_hint: str = Field(default="", max_length=256)
    sort_order: int = Field(default=0, ge=0)


class StyleUpdateReq(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=64)
    style_prompt: str | None = Field(default=None, max_length=2000)
    analysis_hint: str | None = Field(default=None, max_length=256)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


def _style_dict(row: ImageStyle) -> dict:
    return {
        "id": row.id,
        "styleId": row.style_id,
        "label": row.label,
        "stylePrompt": row.style_prompt,
        "analysisHint": row.analysis_hint,
        "sortOrder": row.sort_order,
        "isActive": row.is_active,
        "isSystem": row.is_system,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else "",
    }


@router.get("/styles")
async def list_styles(developer: User = Depends(require_current_developer)):
    async with async_session() as db:
        rows = (await db.execute(select(ImageStyle).order_by(ImageStyle.sort_order.asc()))).scalars().all()
    return {"ok": True, "data": [_style_dict(row) for row in rows]}


@router.post("/styles")
async def create_style(
    body: StyleCreateReq,
    developer: User = Depends(require_current_developer),
):
    from services import style_service
    async with async_session() as db:
        existing = await db.scalar(select(ImageStyle).where(ImageStyle.style_id == body.style_id))
        if existing:
            raise HTTPException(status_code=409, detail="风格标识已存在")
        row = ImageStyle(
            style_id=body.style_id,
            label=body.label,
            style_prompt=body.style_prompt,
            analysis_hint=body.analysis_hint,
            sort_order=body.sort_order,
            is_active=True,
            is_system=False,
        )
        db.add(row)
        await db.flush()
        db.add(SystemEvent(
            level="info",
            event_type="admin_style_created",
            message="developer created image style",
            event_metadata={"actor": developer.username, "styleId": body.style_id},
        ))
        await db.commit()
        await db.refresh(row)
        data = _style_dict(row)
    await style_service.reload_cache()
    return {"ok": True, "data": data}


@router.patch("/styles/{style_id}")
async def update_style(
    style_id: str,
    body: StyleUpdateReq,
    developer: User = Depends(require_current_developer),
):
    from services import style_service
    changes = body.model_dump(exclude_unset=True)
    async with async_session() as db:
        row = await db.scalar(select(ImageStyle).where(ImageStyle.style_id == style_id))
        if row is None:
            raise HTTPException(status_code=404, detail="风格不存在")
        for key, value in changes.items():
            setattr(row, key, value)
        await db.flush()
        db.add(SystemEvent(
            level="info",
            event_type="admin_style_updated",
            message="developer updated image style",
            event_metadata={"actor": developer.username, "styleId": style_id, "fields": list(changes)},
        ))
        await db.commit()
        await db.refresh(row)
        data = _style_dict(row)
    await style_service.reload_cache()
    return {"ok": True, "data": data}


@router.delete("/styles/{style_id}")
async def delete_style(
    style_id: str,
    developer: User = Depends(require_current_developer),
):
    from services import style_service
    async with async_session() as db:
        row = await db.scalar(select(ImageStyle).where(ImageStyle.style_id == style_id))
        if row is None:
            raise HTTPException(status_code=404, detail="风格不存在")
        if row.is_system:
            raise HTTPException(status_code=409, detail="内置风格不可删除")
        await db.delete(row)
        db.add(SystemEvent(
            level="warning",
            event_type="admin_style_deleted",
            message="developer deleted image style",
            event_metadata={"actor": developer.username, "styleId": style_id},
        ))
        await db.commit()
    await style_service.reload_cache()
    return {"ok": True, "data": {"styleId": style_id}}
