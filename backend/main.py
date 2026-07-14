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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from logger import setup_logging

# ── 日志系统 ──
logger = setup_logging()


# ── 生命周期：启动时初始化数据库 + 创建服务单例 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 替代已弃用的 @app.on_event('startup')"""
    from db.database import init_db
    from services.llm_service import LlmService
    from services.search_service import SearchService
    from services.image_service import ImageService
    from services.selection_service import SelectionService
    from services.poem_service import PoemService
    from services.memory_service import MemoryService
    from services.pipeline_service import LetterPipeline

    await init_db()
    logger.info("数据库表已确认")

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

    # shutdown（暂无清理需求）


# ── 创建应用 ──
app = FastAPI(title="故乡来信 API", version="3.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由注册 ──
from auth.routes import router as auth_router
from api.routes import router as api_router

app.include_router(auth_router)
app.include_router(api_router)


# ── 静态资源：前端文件挂载到根路径 ──
_frontend_dir = _os.path.join(_os.path.dirname(__file__), "..", "frontend")
if _os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
