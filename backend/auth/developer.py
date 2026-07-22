"""开发者账号认证依赖。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import decode_token
from db.database import get_db
from db.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_developer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload.get("sub", 0))
    except Exception:
        return None
    user = await db.get(User, user_id)
    if user is None or not user.is_developer:
        return None
    return user


async def require_current_developer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """后台唯一认证入口：必须使用开发者账号签发的 Bearer Token。"""
    user = await get_current_developer(credentials, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要开发者账号登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
