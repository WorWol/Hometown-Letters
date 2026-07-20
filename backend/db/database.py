"""异步数据库引擎 + get_db 依赖注入"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 数据库文件路径
_data_dir = Path(__file__).resolve().parent.parent / "data"
_data_dir.mkdir(exist_ok=True)
_database_path = Path(os.environ.get("SQLITE_DATABASE_PATH", _data_dir / "hometown.db"))
_database_path.parent.mkdir(parents=True, exist_ok=True)
SQLITE_URL = f"sqlite+aiosqlite:///{_database_path}"

engine = create_async_engine(
    SQLITE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def _configure_sqlite(connection, _record) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


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
