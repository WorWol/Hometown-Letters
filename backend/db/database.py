"""异步数据库引擎 + get_db 依赖注入"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base

# 数据库文件路径
_data_dir = Path(__file__).resolve().parent.parent / "data"
_data_dir.mkdir(exist_ok=True)
SQLITE_URL = f"sqlite+aiosqlite:///{_data_dir / 'hometown.db'}"

engine = create_async_engine(
    SQLITE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """创建所有表（开发用；生产用 Alembic）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI 依赖：每次请求注入一个数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
