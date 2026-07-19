"""Ubuntu、Docker 和本地开发环境通用的运行时资源采集。"""
from __future__ import annotations

import os
import time
from pathlib import Path

import psutil


_process = psutil.Process(os.getpid())
_last_cpu = None


def _read_int(path: str) -> int | None:
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def _container_memory() -> dict:
    current = _read_int("/sys/fs/cgroup/memory.current")
    limit = _read_int("/sys/fs/cgroup/memory.max")
    if current is None:
        current = _read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes")
        limit = _read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if limit is not None and limit >= 2**60:
        limit = None
    return {
        "available": current is not None,
        "used": current or 0,
        "limit": limit or 0,
        "usagePercent": round(current / limit * 100, 2) if current and limit else None,
    }

def snapshot() -> dict:
    global _last_cpu
    virtual = psutil.virtual_memory()
    process = _process.memory_info()
    cpu = psutil.cpu_percent(interval=None)
    _last_cpu = cpu
    disk = psutil.disk_usage("/")
    container = _container_memory()
    return {
        "platform": os.uname().sysname if hasattr(os, "uname") else os.name,
        "cpu": {"usagePercent": cpu, "count": psutil.cpu_count() or 1},
        "process": {
            "pid": _process.pid,
            "rss": process.rss,
            "vms": process.vms,
            "memoryPercent": round(_process.memory_percent(), 2),
        },
        "systemMemory": {
            "total": virtual.total,
            "used": virtual.used,
            "available": virtual.available,
            "usagePercent": virtual.percent,
        },
        "containerMemory": container,
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "usagePercent": disk.percent,
        },
        "sampledAt": time.time(),
    }
