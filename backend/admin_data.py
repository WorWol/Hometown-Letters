"""开发者后台的受控数据库浏览与 CRUD API。

这里故意不提供任意 SQL、任意 Python 类名或任意字段写入能力。表和字段均来自
固定 registry；时间、主键、密码哈希和系统审计事件保持只读，避免后台本身成为
新的注入入口。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Boolean, DateTime, Integer, String, Text, delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from auth.developer import require_current_developer
from auth.security import hash_password
from db.database import async_session
from db.models import (
    Base, Hometown, Letter, LetterLike, LetterMemory, LetterSummary,
    Mail, Memory, PastSelfProfile, Postcard, Profile, SystemEvent, User,
)
from services.data_service import delete_letter, delete_postcard, delete_user, recalculate_postcard_count

router = APIRouter(prefix="/api/admin", tags=["admin-data"])

TABLES: dict[str, type[Base]] = {
    "users": User,
    "hometowns": Hometown,
    "profiles": Profile,
    "postcards": Postcard,
    "letters": Letter,
    "letter_summaries": LetterSummary,
    "letter_memories": LetterMemory,
    "memories": Memory,
    "past_self_profiles": PastSelfProfile,
    "mails": Mail,
    "letter_likes": LetterLike,
    "system_events": SystemEvent,
}

READ_ONLY_FIELDS = {"id", "hashed_password", "created_at", "updated_at", "postcard_count", "is_developer"}
READ_ONLY_TABLES = {"system_events"}
MAX_JSON_BYTES = 200_000


def _model(table: str) -> type[Base]:
    model = TABLES.get(table)
    if model is None:
        raise HTTPException(status_code=404, detail="不支持的数据库表")
    return model


def _column_map(model: type[Base]):
    # API 字段使用 ORM 属性名；system_events 的数据库列名是 metadata，
    # 但模型属性是 event_metadata，不能直接 getattr(row, column.name)。
    return {attribute.key: attribute.columns[0] for attribute in model.__mapper__.column_attrs}


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_row(row: Base, model: type[Base]) -> dict[str, Any]:
    return {
        attribute.key: _serialize(getattr(row, attribute.key))
        for attribute in model.__mapper__.column_attrs
        if attribute.key != "hashed_password"
    }


def _field_meta(column: Any, table: str, name: str) -> dict[str, Any]:
    kind = "string"
    if isinstance(column.type, Boolean):
        kind = "boolean"
    elif isinstance(column.type, Integer):
        kind = "integer"
    elif isinstance(column.type, DateTime):
        kind = "datetime"
    elif column.type.__class__.__name__ == "JSON":
        kind = "json"
    is_password = table == "users" and name == "hashed_password"
    writable = (name not in READ_ONLY_FIELDS and table not in READ_ONLY_TABLES) or is_password
    return {
        "name": "password" if is_password else name,
        "type": kind,
        "nullable": bool(column.nullable),
        "required": not column.nullable and column.default is None and column.server_default is None and name != "id",
        "writable": writable or is_password,
        "secret": is_password,
    }


def _parse_value(column: Any, value: Any) -> Any:
    if isinstance(column.type, String) or isinstance(column.type, Text):
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"字段 {column.name} 必须是字符串")
        max_length = getattr(column.type, "length", None)
        if max_length and len(value) > max_length:
            raise HTTPException(status_code=422, detail=f"字段 {column.name} 长度不能超过 {max_length}")
        return value
    if isinstance(column.type, Integer):
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(status_code=422, detail=f"字段 {column.name} 必须是整数")
        return value
    if isinstance(column.type, Boolean):
        if not isinstance(value, bool):
            raise HTTPException(status_code=422, detail=f"字段 {column.name} 必须是布尔值")
        return value
    if isinstance(column.type, DateTime):
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"字段 {column.name} 必须是 ISO 时间字符串")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=f"字段 {column.name} 时间格式不正确") from error
    if column.type.__class__.__name__ == "JSON":
        import json
        if len(json.dumps(value, ensure_ascii=False)) > MAX_JSON_BYTES:
            raise HTTPException(status_code=422, detail=f"字段 {column.name} 内容过大")
        return value
    return value


def _payload(table: str, body: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    model = _model(table)
    columns = _column_map(model)
    allowed = set(columns)
    if table == "users":
        allowed.add("password")
    unknown = set(body) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"不允许的字段: {', '.join(sorted(unknown))}")
    if table in READ_ONLY_TABLES and body:
        raise HTTPException(status_code=405, detail="系统事件仅支持查询")
    values: dict[str, Any] = {}
    for name, value in body.items():
        if table == "users" and name == "password":
            if not creating and value == "":
                continue
            if not isinstance(value, str) or not 8 <= len(value) <= 72:
                raise HTTPException(status_code=422, detail="password 长度应为 8-72 个字符")
            values["hashed_password"] = hash_password(value)
            continue
        column = columns[name]
        if name in READ_ONLY_FIELDS:
            raise HTTPException(status_code=422, detail=f"字段 {name} 只读")
        if value is None and not column.nullable:
            raise HTTPException(status_code=422, detail=f"字段 {name} 不能为空")
        values[name] = None if value is None else _parse_value(column, value)
    if creating:
        required = [column.key for column in model.__table__.columns if column.key != "id" and not column.nullable and column.default is None and column.server_default is None]
        missing = [name for name in required if name not in values and name != "hashed_password"]
        if table == "users" and "hashed_password" not in values:
            missing.append("password")
        if missing:
            raise HTTPException(status_code=422, detail=f"缺少必填字段: {', '.join(missing)}")
    return values


def _search_clause(model: type[Base], term: str):
    columns = [column for column in model.__table__.columns if isinstance(column.type, (String, Text))]
    return or_(*(column.contains(term) for column in columns)) if columns else None


@router.get("/schema")
async def schema(developer: User = Depends(require_current_developer)):
    return {"ok": True, "data": {table: {"table": table, "fields": [_field_meta(column, table, attribute.key) for attribute in model.__mapper__.column_attrs for column in attribute.columns]}
                                  for table, model in TABLES.items()}}


@router.get("/data/{table}")
async def list_rows(
    table: str,
    q: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="id"),
    direction: str = Query(default="desc"),
    developer: User = Depends(require_current_developer),
):
    model = _model(table)
    columns = _column_map(model)
    if order not in columns:
        raise HTTPException(status_code=422, detail="不支持的排序字段")
    if direction not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="排序方向不正确")
    async with async_session() as db:
        query = select(model)
        primary_key = next(iter(model.__table__.primary_key.columns))
        count_query = select(func.count(primary_key))
        clause = _search_clause(model, q.strip()) if q.strip() else None
        if clause is not None:
            query = query.where(clause)
            count_query = count_query.where(clause)
        sort_column = columns[order]
        query = query.order_by(sort_column.asc() if direction == "asc" else sort_column.desc()).offset(offset).limit(limit)
        rows = (await db.execute(query)).scalars().all()
        total = await db.scalar(count_query) or 0
    return {"ok": True, "data": {"items": [_serialize_row(row, model) for row in rows], "total": total, "offset": offset, "limit": limit}}


@router.get("/data/{table}/{row_id}")
async def get_row(table: str, row_id: int, developer: User = Depends(require_current_developer)):
    model = _model(table)
    async with async_session() as db:
        row = await db.get(model, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="数据不存在")
    return {"ok": True, "data": _serialize_row(row, model)}


@router.post("/data/{table}")
async def create_row(table: str, body: dict[str, Any], developer: User = Depends(require_current_developer)):
    model = _model(table)
    values = _payload(table, body, creating=True)
    async with async_session() as db:
        row = model(**values)
        db.add(row)
        try:
            await db.commit()
            await db.refresh(row)
        except IntegrityError as error:
            await db.rollback()
            raise HTTPException(status_code=409, detail="数据违反唯一性或关联约束") from error
    return {"ok": True, "data": _serialize_row(row, model)}


@router.patch("/data/{table}/{row_id}")
async def update_row(table: str, row_id: int, body: dict[str, Any], developer: User = Depends(require_current_developer)):
    model = _model(table)
    values = _payload(table, body, creating=False)
    async with async_session() as db:
        row = await db.get(model, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="数据不存在")
        for name, value in values.items():
            setattr(row, name, value)
        try:
            await db.commit()
            await db.refresh(row)
        except IntegrityError as error:
            await db.rollback()
            raise HTTPException(status_code=409, detail="数据违反唯一性或关联约束") from error
    return {"ok": True, "data": _serialize_row(row, model)}


@router.delete("/data/{table}/{row_id}")
async def delete_row(table: str, row_id: int, developer: User = Depends(require_current_developer)):
    model = _model(table)
    if table in READ_ONLY_TABLES:
        raise HTTPException(status_code=405, detail="系统事件仅支持查询")
    async with async_session() as db:
        row = await db.get(model, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="数据不存在")
        try:
            if model is User:
                await delete_user(db, row)
            elif model is Postcard:
                await delete_postcard(db, row)
            elif model is Letter:
                await delete_letter(db, row)
            elif model is LetterSummary:
                await db.execute(delete(LetterMemory).where(LetterMemory.summary_id == row_id))
                await db.delete(row)
            else:
                await db.delete(row)
            await db.commit()
        except IntegrityError as error:
            await db.rollback()
            raise HTTPException(status_code=409, detail="无法删除：仍有其他数据引用此记录") from error
        except Exception:
            await db.rollback()
            raise HTTPException(status_code=502, detail="删除失败，数据库未提交")
    return {"ok": True, "data": {"id": row_id, "table": table}}


@router.post("/users/{user_id}/recalculate-postcard-count")
async def recalculate_user_postcard_count(user_id: int, developer: User = Depends(require_current_developer)):
    async with async_session() as db:
        if await db.get(User, user_id) is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        count = await recalculate_postcard_count(db, user_id)
        await db.commit()
    return {"ok": True, "data": {"userId": user_id, "postcardCount": count}}
