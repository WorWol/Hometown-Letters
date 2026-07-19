"""故乡来信 — FastAPI 后端（统一架构）

流程：接收到信请求 →
  1. 信件分析（提取 core_place）
  2. SearchService 搜索图片
  3. SelectionService 筛选相关图片
  4. PoemService 生成诗歌 / 标题 / 正文 / 图像提示词
  5. ImageService 生成图像（以上游图片做参考）
  6. 存储，返回
"""
from __future__ import annotations

import os as _os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from logger import setup_logging

# ── 日志系统 ──
logger = setup_logging()


# ── 生命周期：启动时初始化数据库 + 创建服务单例 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 替代已弃用的 @app.on_event('startup')"""
    from db.database import upgrade_db
    from services.llm_service import LlmService
    from services.search_service import SearchService
    from services.image_service import ImageService
    from services.selection_service import SelectionService
    from services.poem_service import PoemService
    from services.memory_service import MemoryService
    from services.pipeline_service import LetterPipeline
    from services.monitoring_service import cleanup_old_events
    from services.image_storage import validate_storage_config

    validate_storage_config()
    await upgrade_db()
    logger.info("数据库迁移已完成")
    deleted_events = await cleanup_old_events()
    logger.info("本地监控事件清理完成，删除 %s 条", deleted_events)

    async def event_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(6 * 60 * 60)
            try:
                deleted = await cleanup_old_events()
                logger.info("本地监控事件定期清理完成，删除 %s 条", deleted)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("本地监控事件定期清理失败")

    cleanup_task = asyncio.create_task(event_cleanup_loop())

    # 创建服务单例，存入 app.state 供 DI 使用
    llm = LlmService()
    search = SearchService()
    image_gen = ImageService()
    selection_svc = SelectionService()
    poem_svc = PoemService(llm)
    memory_svc = MemoryService()

    app.state.llm = llm
    app.state.search = search
    app.state.image_gen = image_gen

    app.state.pipeline = LetterPipeline(
        llm=llm,
        search=search,
        image_gen=image_gen,
        selection_svc=selection_svc,
        poem_svc=poem_svc,
        memory_svc=memory_svc,
    )
    logger.info("服务单例已注入 app.state")

    yield

    cleanup_task.cancel()
    await asyncio.gather(cleanup_task, return_exceptions=True)


# ── 创建应用 ──
app = FastAPI(title="故乡来信 API", version="3.1.0", lifespan=lifespan)
_allowed_origins = [item.strip() for item in settings.allowed_origins.split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=bool(_allowed_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由注册 ──
from auth.routes import router as auth_router
from api.routes import router as api_router
from admin import router as admin_router

app.include_router(auth_router)
app.include_router(api_router)
app.include_router(admin_router)


# ── 静态资源缓存中间件 ──
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, RedirectResponse, Response

_CACHE_EXTENSIONS = {".css", ".js", ".webp", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff2"}
_CACHE_SECONDS = 86400  # 1 天

class StaticCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if any(path.endswith(ext) for ext in _CACHE_EXTENSIONS):
            response.headers["Cache-Control"] = f"public, max-age={_CACHE_SECONDS}, immutable"
        return response

app.add_middleware(StaticCacheMiddleware)
from middleware import ApiMetricsMiddleware
app.add_middleware(ApiMetricsMiddleware)


@app.get("/assets/{asset_path:path}", include_in_schema=False)
async def serve_frontend_asset(asset_path: str):
    """Keep frontend asset URLs stable while switching their storage to OSS."""
    if settings.storage_backend.lower() == "oss":
        from services.image_storage import get_asset_url

        return RedirectResponse(get_asset_url(asset_path), status_code=307)

    local_path = (Path(_frontend_dir) / "assets" / asset_path).resolve()
    assets_root = (Path(_frontend_dir) / "assets").resolve()
    if assets_root not in local_path.parents or not local_path.is_file():
        return Response(status_code=404)
    return FileResponse(local_path)


# ── 静态资源：前端文件挂载到根路径 ──
_frontend_dir = _os.path.join(_os.path.dirname(__file__), "..", "frontend")
_media_dir = _os.path.join(_os.path.dirname(__file__), "generated_images")
if _os.path.isdir(_media_dir):
    app.mount("/media", StaticFiles(directory=_media_dir), name="media")
if _os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
