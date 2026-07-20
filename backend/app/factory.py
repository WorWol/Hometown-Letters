"""FastAPI application factory."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, RedirectResponse, Response

from app.lifespan import lifespan
from config import settings
from middleware import ApiMetricsMiddleware


class StaticCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path.lower()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()

        # HTML 是资源入口，必须每次向服务端确认，才能拿到新版本的 JS/CSS。
        # 否则浏览器可能缓存旧 HTML，继续引用已经不存在或已改名的脚本。
        if content_type == "text/html" or path == "/" or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-store"
        elif path.endswith((".css", ".js")):
            # JS/CSS 使用 ETag/Last-Modified 做快速协商缓存，但不允许永久缓存。
            # 这样部署后即使资源 URL 没变，浏览器也会自动确认内容是否更新。
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        elif path.endswith((".webp", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff2")):
            response.headers["Cache-Control"] = "public, max-age=86400, immutable"
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="故乡来信 API", version="3.1.0", lifespan=lifespan)
    allowed_origins = [item.strip() for item in settings.allowed_origins.split(",") if item.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=bool(allowed_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(StaticCacheMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ApiMetricsMiddleware)

    from admin import router as admin_router
    from admin_data import router as admin_data_router
    from api.router import router as api_router
    from auth.routes import router as auth_router

    app.include_router(auth_router)
    app.include_router(api_router)
    app.include_router(admin_router)
    app.include_router(admin_data_router)

    frontend_dir = Path(__file__).resolve().parents[1] / ".." / "frontend"
    media_dir = Path(__file__).resolve().parents[1] / "generated_images"

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def serve_frontend_asset(asset_path: str):
        if settings.storage_backend.lower() == "oss":
            from storage import asset_url
            return RedirectResponse(asset_url(asset_path), status_code=307)
        assets_root = (frontend_dir / "assets").resolve()
        local_path = (assets_root / asset_path).resolve()
        if assets_root not in local_path.parents or not local_path.is_file():
            return Response(status_code=404)
        return FileResponse(local_path)

    if media_dir.is_dir():
        app.mount("/media", StaticFiles(directory=media_dir), name="media")
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app
