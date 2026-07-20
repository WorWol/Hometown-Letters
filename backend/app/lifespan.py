"""Application startup and shutdown lifecycle."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from logger import setup_logging

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared services and run lightweight maintenance tasks."""
    from services.image_service import ImageService
    from storage import validate_config
    from services.llm_service import LlmService
    from services.memory_service import MemoryService
    from services.monitoring_service import cleanup_old_events
    from services.pipeline_service import LetterPipeline
    from services.poem_service import PoemService
    from services.search_service import SearchService
    from services.selection_service import SelectionService

    validate_config()
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

    async def metrics_flush_loop() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                from services import persistent_metrics
                await persistent_metrics.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("API 指标批量写入失败")

    async def storage_retry_loop() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                from services.storage_tasks import retry_pending
                await retry_pending()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("OSS 删除任务重试失败")

    llm = LlmService()
    app.state.llm = llm
    app.state.search = SearchService()
    app.state.image_gen = ImageService()
    app.state.pipeline = LetterPipeline(
        llm=llm,
        search=app.state.search,
        image_gen=app.state.image_gen,
        selection_svc=SelectionService(),
        poem_svc=PoemService(llm),
        memory_svc=MemoryService(),
    )
    cleanup_task = asyncio.create_task(event_cleanup_loop())
    metrics_task = asyncio.create_task(metrics_flush_loop())
    storage_task = asyncio.create_task(storage_retry_loop())
    logger.info("服务单例已注入 app.state")

    try:
        yield
    finally:
        cleanup_task.cancel()
        metrics_task.cancel()
        storage_task.cancel()
        await asyncio.gather(cleanup_task, metrics_task, storage_task, return_exceptions=True)
        from services import persistent_metrics
        await persistent_metrics.flush()
