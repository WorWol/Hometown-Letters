"""认证路由 — /api/auth/register | login | me"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.security import create_token, hash_password, verify_password
from db.database import get_db
from db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    user_id: int
    username: str
    current_day: int


@router.post("/register")
async def register(body: AuthRequest, db: AsyncSession = Depends(get_db)):
    if not body.username or not body.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="用户名和密码不能为空",
        )

    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        current_day=0,
    )
    db.add(user)
    await db.flush()
    token = create_token(user.id, user.username)
    return {
        "ok": True,
        "data": {"token": token, "user_id": user.id},
    }


@router.post("/login")
async def login(body: AuthRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

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
        },
    }
