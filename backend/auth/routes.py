"""认证路由 — /api/auth/register | login | me"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.security import create_token, hash_password, verify_password
from config import settings
from db.database import get_db
from db.models import SystemEvent, User
from services.rate_limiter import check_login_failure, check_registration, clear_login_failures

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)


class UserResponse(BaseModel):
    user_id: int
    username: str
    current_day: int


def _client_ip(request: Request) -> str:
    """直接部署时只使用 TCP 对端地址，不盲信用户可伪造的 X-Forwarded-For。"""
    return request.client.host if request.client else "unknown"


def _validate_registration(body: AuthRequest) -> str:
    username = body.username.strip()
    if not re.fullmatch(r"[\w\-\u4e00-\u9fff]{2,32}", username, flags=re.UNICODE):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="用户名需为 2-32 个中文、字母、数字、下划线或连字符",
        )
    if not body.password.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="密码不能为空",
        )
    if len(body.password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="密码过长，请控制在 72 字节以内",
        )
    return username


def _rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="操作过于频繁，请稍后再试",
        headers={"Retry-After": str(retry_after)},
    )


@router.post("/register")
async def register(request: Request, body: AuthRequest, db: AsyncSession = Depends(get_db)):
    username = _validate_registration(body)
    rate = await check_registration(_client_ip(request), username)
    if not rate.allowed:
        raise _rate_limited(rate.retry_after)

    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    user = User(
        username=username,
        hashed_password=hash_password(body.password),
        current_day=0,
        postcard_limit=settings.default_postcard_limit,
    )
    db.add(user)
    await db.flush()
    db.add(SystemEvent(
        level="info",
        event_type="user_registered",
        message="user registered",
        user_id=user.id,
    ))
    token = create_token(user.id, user.username)
    return {
        "ok": True,
        "data": {"token": token, "user_id": user.id},
    }


@router.post("/login")
async def login(request: Request, body: AuthRequest, db: AsyncSession = Depends(get_db)):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if len(body.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    ip = _client_ip(request)
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        rate = await check_login_failure(ip, username)
        if not rate.allowed:
            raise _rate_limited(rate.retry_after)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    await clear_login_failures(ip, username)
    token = create_token(user.id, user.username)
    return {
        "ok": True,
        "data": {"token": token, "user_id": user.id},
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "ok": True,
        "data": {
            "user_id": user.id,
            "username": user.username,
            "current_day": user.current_day,
            "postcard_limit": user.postcard_limit,
            "postcard_count": user.postcard_count,
        },
    }
