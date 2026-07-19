"""日志系统设置 — 控制台 + 文件双写，按日期轮转"""
from __future__ import annotations

import logging
import logging.handlers
import json
from pathlib import Path

from config import settings

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "hometown.log"


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("hometown")
    logger.setLevel(logging.DEBUG)
    log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # lifespan 在测试和开发环境可能被重复调用，避免重复添加 handler。
    if logger.handlers:
        return logger

    # 控制台 handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(log_fmt)
    logger.addHandler(console)

    # 文件 handler — 按日期轮转，保留 7 天
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=max(settings.log_retention_days, 1),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_fmt)
    logger.addHandler(file_handler)

    logger.info("日志系统已初始化，日志文件: %s", LOG_FILE)

    # 把 uvicorn 的访问日志也写入文件
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.addHandler(file_handler)
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.addHandler(file_handler)

    return logger


def record_event(level: str, event_type: str, message: str, *, user_id: int | None = None,
                 request_id: str = "", metadata: dict | None = None) -> None:
    """写入带结构化上下文的本地日志，数据库事件由业务层显式记录。"""
    logger = logging.getLogger("hometown")
    payload = {
        "event_type": event_type,
        "user_id": user_id,
        "request_id": request_id,
        "metadata": metadata or {},
    }
    getattr(logger, level.lower(), logger.info)(
        "%s | %s", message, json.dumps(payload, ensure_ascii=False)
    )
