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

        # 重定向响应（OSS 模式下 /assets 跳转到签名 URL）不能长缓存：
        # 签名 URL 15 分钟过期，缓存重定向会让浏览器用过期签名，图片加载失败。
        if response.status_code in (301, 302, 303, 307, 308):
            response.headers["Cache-Control"] = "no-store"
            return response

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

    from api.router import router as api_router
    from auth.routes import router as auth_router

    app.include_router(auth_router)
    app.include_router(api_router)

    frontend_dir = Path(__file__).resolve().parents[1] / ".." / "frontend"
    media_dir = Path(__file__).resolve().parents[1] / "generated_images"

    _asset_cache: dict[str, tuple[bytes, str]] = {}

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def serve_frontend_asset(asset_path: str):
        if settings.storage_backend.lower() == "oss":
            # OSS 模式：后端代理下载（绕过浏览器系统代理连不上 OSS 的问题）+ 内存缓存
            if asset_path in _asset_cache:
                content, content_type = _asset_cache[asset_path]
                response = Response(content, media_type=content_type)
                response.headers["Cache-Control"] = "public, max-age=86400"
                return response
            from storage import asset_url
            import httpx
            url = asset_url(asset_path)
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
                    resp = await client.get(url, follow_redirects=True)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "image/png")
                        _asset_cache[asset_path] = (resp.content, content_type)
                        response = Response(resp.content, media_type=content_type)
                        response.headers["Cache-Control"] = "public, max-age=86400"
                        return response
            except Exception:
                pass
            return Response(status_code=502)
        assets_root = (frontend_dir / "app" / "assets").resolve()
        local_path = (assets_root / asset_path).resolve()
        if assets_root not in local_path.parents or not local_path.is_file():
            return Response(status_code=404)
        return FileResponse(local_path)

    # 旧入口 URL 兼容：开发者平台 html 已移入 admin/ 子目录，保留重定向防止书签失效。
    @app.get("/admin.html", include_in_schema=False)
    async def _legacy_admin_entry():
        return RedirectResponse("/admin/admin.html")

    @app.get("/admin-login.html", include_in_schema=False)
    async def _legacy_admin_login_entry():
        return RedirectResponse("/admin/admin-login.html")

    if settings.storage_backend.lower() == "oss":
        # OSS 模式：/media 代理 OSS（绕过浏览器系统代理 + 签名过期）+ 内存缓存
        _media_cache: dict[str, tuple[bytes, str]] = {}

        @app.get("/media/{object_key:path}", include_in_schema=False)
        async def serve_media(object_key: str):
            if object_key in _media_cache:
                content, content_type = _media_cache[object_key]
                response = Response(content, media_type=content_type)
                response.headers["Cache-Control"] = "public, max-age=86400"
                return response
            from storage import _bucket
            import httpx
            bucket = _bucket("public")
            if not bucket:
                return Response(status_code=502)
            url = bucket.sign_url("GET", object_key, settings.oss_url_expire_seconds)
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
                    resp = await client.get(url, follow_redirects=True)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "image/webp")
                        _media_cache[object_key] = (resp.content, content_type)
                        response = Response(resp.content, media_type=content_type)
                        response.headers["Cache-Control"] = "public, max-age=86400"
                        return response
            except Exception:
                pass
            return Response(status_code=502)
    elif media_dir.is_dir():
        app.mount("/media", StaticFiles(directory=media_dir), name="media")
    admin_dir = frontend_dir / "admin"
    app_dir = frontend_dir / "app"
    if admin_dir.is_dir():
        app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")
    if app_dir.is_dir():
        app.mount("/", StaticFiles(directory=app_dir, html=True), name="frontend")
    return app
