"""进程内 API 请求统计。

只保存聚合计数，不保存请求体、Authorization 或用户隐私数据。服务重启后统计归零，
适合开发者后台查看实时状态；需要长期趋势时再接入独立的时序存储。
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass


_ID_SEGMENT = re.compile(r"^(?:\d+|[0-9a-f]{8,})$", re.IGNORECASE)


def normalize_path(path: str) -> str:
    """降低动态 URL 的基数，避免每个 ID 都产生一个独立指标。"""
    parts = ["<id>" if _ID_SEGMENT.match(part) else part for part in path.split("/")]
    return "/".join(parts) or "/"


@dataclass
class _Metric:
    count: int = 0
    success: int = 0
    client_errors: int = 0
    server_errors: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    last_status: int = 0
    last_at: float = 0.0


class ApiMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._total = _Metric()
        self._routes: dict[tuple[str, str], _Metric] = defaultdict(_Metric)

    def record(self, method: str, path: str, status_code: int, elapsed_ms: float) -> None:
        now = time.time()
        key = (method.upper(), normalize_path(path))
        with self._lock:
            for metric in (self._total, self._routes[key]):
                metric.count += 1
                metric.success += int(200 <= status_code < 400)
                metric.client_errors += int(400 <= status_code < 500)
                metric.server_errors += int(status_code >= 500)
                metric.total_ms += elapsed_ms
                metric.max_ms = max(metric.max_ms, elapsed_ms)
                metric.last_status = status_code
                metric.last_at = now

    @staticmethod
    def _serialize(metric: _Metric) -> dict:
        return {
            "count": metric.count,
            "success": metric.success,
            "clientErrors": metric.client_errors,
            "serverErrors": metric.server_errors,
            "averageMs": round(metric.total_ms / metric.count, 2) if metric.count else 0,
            "maxMs": round(metric.max_ms, 2),
            "lastStatus": metric.last_status,
            "lastAt": metric.last_at,
        }

    def snapshot(self, limit: int = 100) -> dict:
        with self._lock:
            rows = [
                {
                    "method": method,
                    "path": path,
                    **self._serialize(metric),
                }
                for (method, path), metric in self._routes.items()
            ]
            rows.sort(key=lambda item: (item["count"], item["lastAt"]), reverse=True)
            return {
                "startedAt": self._started_at,
                "uptimeSeconds": int(time.time() - self._started_at),
                "total": self._serialize(self._total),
                "routes": rows[:limit],
            }


api_metrics = ApiMetrics()
