"""应用级中间件。"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from services.api_metrics import api_metrics


class ApiMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            api_metrics.record(
                request.method,
                request.url.path,
                status_code,
                (time.perf_counter() - started) * 1000,
            )
