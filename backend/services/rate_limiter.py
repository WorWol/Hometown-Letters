"""轻量级进程内限流器。

当前项目在 ECS 上以单个应用容器运行，进程内限流足够覆盖注册和登录爆破。
如果未来扩展为多副本，应把同样的计数器迁移到 Redis，避免每个副本各自放行。
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    retry_after: int = 0


class InMemoryRateLimiter:
    def __init__(self, max_keys: int = 20_000) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._max_keys = max_keys

    async def hit(self, key: str, limit: int, window_seconds: int) -> LimitResult:
        now = time.monotonic()
        async with self._lock:
            bucket = self._events[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(bucket[0] + window_seconds - now + 0.999))
                return LimitResult(False, retry_after)
            bucket.append(now)
            self._trim_keys()
            return LimitResult(True)

    async def clear(self, *keys: str) -> None:
        async with self._lock:
            for key in keys:
                self._events.pop(key, None)

    def _trim_keys(self) -> None:
        if len(self._events) <= self._max_keys:
            return
        empty = [key for key, values in self._events.items() if not values]
        for key in empty[: max(1, len(empty) // 2)]:
            self._events.pop(key, None)


auth_rate_limiter = InMemoryRateLimiter()


async def check_registration(ip: str, username: str) -> LimitResult:
    """限制 IP 和用户名组合，降低批量注册和单账号撞库压力。"""
    checks = (
        (f"register:ip:hour:{ip}", 3, 60 * 60),
        (f"register:ip:day:{ip}", 5, 24 * 60 * 60),
        (f"register:user:{username.casefold()}", 5, 15 * 60),
    )
    for key, limit, window in checks:
        result = await auth_rate_limiter.hit(key, limit, window)
        if not result.allowed:
            return result
    return LimitResult(True)


async def check_login_failure(ip: str, username: str) -> LimitResult:
    """限制失败登录次数；成功登录时会清理对应失败计数。"""
    checks = (
        (f"login:ip:{ip}", 10, 15 * 60),
        (f"login:user:{username.casefold()}", 5, 15 * 60),
    )
    for key, limit, window in checks:
        result = await auth_rate_limiter.hit(key, limit, window)
        if not result.allowed:
            return result
    return LimitResult(True)


async def clear_login_failures(ip: str, username: str) -> None:
    await auth_rate_limiter.clear(
        f"login:ip:{ip}",
        f"login:user:{username.casefold()}",
    )
