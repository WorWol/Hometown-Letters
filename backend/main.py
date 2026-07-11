"""故乡来信 — FastAPI 后端（薄编排层）

流程：接收到信请求 →
  1. LandmarkService 确保地标库存在（为空则 LLM 播种）
  2. LandmarkService 检查是否用完（用完则 LLM 补充）
  3. LandmarkService 选出本次地标（可用 LLM 匹配信件）
  4. SearchService 搜索图片
  5. SelectionService 筛选相关图片
  6. PoemService 生成诗歌 / 标题 / 正文 / 图像提示词
  7. ImageService 生成图像（以上游图片做参考）
  8. 标记地标已使用，存储，返回
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import traceback
import base64
import os
from typing import Any
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

# ── 日志系统：控制台 + 文件双写 ──
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "hometown.log"

logger = logging.getLogger("hometown")
logger.setLevel(logging.DEBUG)
log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 控制台 handler
_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(log_fmt)
logger.addHandler(_console)

# 文件 handler — 按日期轮转，保留 7 天
_file = logging.handlers.TimedRotatingFileHandler(
    LOG_FILE, when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
_file.setLevel(logging.DEBUG)
_file.setFormatter(log_fmt)
logger.addHandler(_file)

logger.info("日志系统已初始化，日志文件: %s", LOG_FILE)

# 把 uvicorn 的访问日志也写入文件
_uvicorn_log = logging.getLogger("uvicorn.access")
_uvicorn_log.addHandler(_file)
_uvicorn_log = logging.getLogger("uvicorn.error")
_uvicorn_log.addHandler(_file)

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.search_service import SearchService
from services.llm_service import LlmService
from services.image_service import ImageService
from services.landmark_service import LandmarkService
from services.selection_service import SelectionService
from services.poem_service import PoemService
from store import store

# ── 初始化服务 ──

app = FastAPI(title="故乡来信 API", version="2.0.0")
app.add_middleware(CORSMiddleware,
                   allow_origins=["*"],
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"])

llm = LlmService()
search = SearchService()
image_gen = ImageService()
landmark_svc = LandmarkService(llm)
selection_svc = SelectionService(llm)
poem_svc = PoemService(llm)

# ── 注册 v2 路由 ──
from auth.routes import router as auth_router
from api_v2.routes import router as v2_router

app.include_router(auth_router)
app.include_router(v2_router)


# ── 启动事件：初始化数据库 ──
@app.on_event("startup")
async def startup_db():
    from db.database import init_db
    await init_db()
    logger.info("数据库表已确认（如未创建则自动创建）")


# ── 辅助函数 ──

async def _search_landmark_context(hometown: dict) -> str:
    """联网搜索该地区的地标信息，返回上下文文本"""
    city = hometown.get("city", "")
    county = hometown.get("county", "")
    logger.info("search_landmark_context city=%s county=%s", city, county)
    if not city and not county:
        logger.warning("empty hometown, skipping web search for landmarks")
        return ""
    queries = [
        f"{city} 地标建筑 景点",
        f"{city} 旅游景点 推荐",
    ]
    if county:
        queries.append(f"{county} 地标 日常 老街")
        queries.append(f"{county} 公园 学校 市场")

    results = []
    for q in queries[:3]:
        try:
            items = await search.search_text(q, num=5)
            for item in items[:3]:
                text = item.get("content", "").strip()
                if text and len(text) > 10:
                    results.append(f"[{q}] {text[:150]}")
        except Exception:
            pass

    return "\n".join(results[:12]) if results else ""


# ── 数据模型 ──

class LetterRequest(BaseModel):
    user_id: str = "default"
    text: str
    place_hint: str = ""
    mood_hint: str = ""


class MemoryRequest(BaseModel):
    user_id: str = "default"
    text: str
    tags: list[str] = []
    place_hint: str = ""


class HometownInitRequest(BaseModel):
    user_id: str = "default"
    province: str = ""
    city: str = ""
    county: str = ""
    hometown_name: str = ""


# ── API ──

@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "service": "hometown-letters-v2"}


@app.post("/api/hometown/init")
async def init_hometown(body: HometownInitRequest) -> dict:
    hometown = {
        "province": body.province,
        "city": body.city,
        "county": body.county,
        "hometownName": body.hometown_name or f"{body.province}{body.city}{body.county}",
    }
    profile = {"hometownName": hometown["hometownName"],
               "province": body.province,
               "city": body.city, "county": body.county}
    store.init_hometown(body.user_id, hometown, profile)

    # 联网搜索地标信息，再播种地标库
    search_ctx = await _search_landmark_context(hometown)
    landmark_svc.ensure_landmarks(body.user_id, hometown, store, search_ctx)
    return {"ok": True, "data": {"hometown": hometown, "profile": profile}}


@app.post("/api/letter/send")
async def send_letter(body: LetterRequest) -> dict:
    """核心流程：地标 → 搜图 → 筛选 → 生诗 → 生图"""
    logger.info("=== send_letter start ===")
    logger.info("text=%s place_hint=%s mood_hint=%s",
                body.text[:50], body.place_hint, body.mood_hint)
    try:
        user_id = body.user_id
        state = store.get_game_state(user_id)
        hometown = state.get("hometown", {})
        logger.info("user=%s has_hometown=%s landmarks_count=%s",
                    user_id, bool(hometown), len(state.get("landmarks", [])))

        # 1. 确保地标库存在
        logger.info("STEP 1: ensure_landmarks")
        landmarks = landmark_svc.ensure_landmarks(user_id, hometown, store)
        logger.info("landmarks count=%s", len(landmarks))
        if not landmarks:
            return {"ok": False, "error": "无法生成地标库，请先设置故乡信息"}

        # 2. 检查是否用完，联网搜索后再补充
        logger.info("STEP 2: check exhausted + web search")
        search_ctx = await _search_landmark_context(hometown)
        logger.info("search_ctx length=%s", len(search_ctx))
        landmark_svc.refresh_if_exhausted(user_id, hometown, store, search_ctx)

        # 3. 选择本次地标（结合书信内容和地点提示）
        logger.info("STEP 3: select landmark (text=%s, place_hint=%s)",
                    body.text[:30], body.place_hint)
        landmark = landmark_svc.get_next_landmark(
            user_id, store, body.text, body.place_hint
        )
        logger.info("selected landmark: %s", landmark.get("name") if landmark else "NONE")
        if not landmark:
            return {"ok": False, "error": "没有可用的地标"}

        lm_name = landmark.get("name", "故乡")
        lm_desc = landmark.get("description", "")
        lm_id = landmark.get("id", "")

        # 4. 搜索图片
        logger.info("STEP 4: search images for %s", lm_name)
        geo = f"{hometown.get('province','')} {hometown.get('city','')} {hometown.get('county','')}"
        search_query = f"{geo} {lm_name}".strip()
        logger.info("search_query=%s", search_query)
        raw_image_urls = await search.search_images(search_query, num=6)
        logger.info("raw images found=%s", len(raw_image_urls))

        # 5. 筛选相关图片
        logger.info("STEP 5: filter images")
        filtered_urls = selection_svc.filter_relevant_images(raw_image_urls, landmark)
        logger.info("filtered images=%s", len(filtered_urls))

        # 6. 搜索文字资料
        logger.info("STEP 6: search text")
        text_info = await search.search_text(search_query, num=3)
        context_str = "；".join(
            [item["content"][:120] for item in text_info[:3]]
        ) if text_info else lm_desc
        logger.info("context_str length=%s", len(context_str))

        # 7. 生成诗 / 标题 / 正文
        logger.info("STEP 7: generate poem/title/body")
        poem = poem_svc.generate_poem(landmark, context_str)
        logger.info("poem generated, length=%s", len(poem))
        title = poem_svc.generate_title(landmark, poem)
        body_text = poem_svc.generate_body(landmark, poem, body.text)
        logger.info("title=%s body_length=%s", title, len(body_text))

        # 8. 生成英文图像提示词
        logger.info("STEP 8: image prompt")
        image_prompt = poem_svc.generate_image_prompt(landmark, context_str)
        logger.info("prompt generated, length=%s", len(image_prompt))

        # 9. 火山引擎生图（用筛选后的图片做参考）
        logger.info("STEP 9: generate image")
        from services.image_service import ImageService as ImgSvc

        ref_images = []
        for i, url in enumerate(filtered_urls[:2]):
            logger.info("downloading ref image %s", i+1)
            encoded = await ImgSvc.download_and_encode(url)
            if encoded:
                ref_images.append(encoded)
                logger.info("ref image %s encoded, length=%s", i+1, len(encoded))

        gen_result = await image_gen.generate(
            image_prompt,
            reference_images=ref_images,
        )
        logger.info("gen_result ok=%s has_url=%s error=%s",
                    gen_result.get("ok"), bool(gen_result.get("url")),
                    gen_result.get("error", ""))

        # 10. 生成 postcard ID
        pc_id = f"pc-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 11. 下载生成的图片到本地缓存
        local_image_url = ""
        gen_image_url = gen_result.get("url", "")
        if gen_image_url:
            try:
                logger.info("downloading generated image to local cache...")
                image_data = await ImgSvc.download_image_bytes(gen_image_url)
                if image_data:
                    store.cache_image(pc_id, image_data, "image/jpeg")
                    local_image_url = f"http://127.0.0.1:8787/api/image/{pc_id}"
                    logger.info("image cached locally, size=%s bytes", len(image_data))
                else:
                    logger.warning("failed to download generated image, using CDN URL")
                    local_image_url = gen_image_url
            except Exception as dl_err:
                logger.warning("image download error: %s", dl_err)
                local_image_url = gen_image_url
        elif filtered_urls:
            # 生图失败，用搜索结果兜底，也尝试下载到本地
            logger.info("gen failed, using fallback from search results")
            try:
                fallback_data = await ImgSvc.download_image_bytes(filtered_urls[0])
                if fallback_data:
                    store.cache_image(pc_id, fallback_data, "image/jpeg")
                    local_image_url = f"http://127.0.0.1:8787/api/image/{pc_id}"
                    logger.info("fallback image cached locally")
            except Exception:
                local_image_url = filtered_urls[0]

        # 12. 组装明信片
        logger.info("STEP 12: assemble postcard")
        now_ts = datetime.now().isoformat()
        postcard = {
            "id": pc_id,
            "title": title,
            "body": body_text,
            "poem": poem,
            "place": lm_name,
            "landmarkId": lm_id,
            "landmarkDescription": lm_desc,
            "mood": body.mood_hint or "平静",
            "imageUrl": local_image_url or gen_image_url or "",
            "imagePrompt": image_prompt,
            "searchImageUrls": filtered_urls,
            "createdAt": now_ts,
            "letterText": body.text,
        }

        if not gen_result.get("ok") or not postcard["imageUrl"]:
            if filtered_urls:
                postcard["imageUrl"] = filtered_urls[0]
                postcard["usedFallback"] = True
                logger.info("used fallback image from search")

        # 13. 标记地标已使用 + 存储
        logger.info("STEP 13: save")
        store.mark_landmark_used(user_id, lm_id)
        store.add_postcard(user_id, postcard)
        store.add_letter(user_id, {
            "id": f"ltr-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "text": body.text, "place": lm_name,
            "mood": body.mood_hint or "平静",
            "timestamp": now_ts,
        })

        logger.info("=== send_letter SUCCESS ===")
        return {"ok": True, "data": postcard}

    except Exception as e:
        tb = traceback.format_exc()
        logger.error("=== send_letter ERROR ===\n%s", tb)
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


@app.post("/api/memory/save")
async def save_memory(body: MemoryRequest) -> dict:
    memory = {
        "id": f"mem-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text": body.text, "tags": body.tags,
        "placeHint": body.place_hint,
        "timestamp": datetime.now().isoformat(),
        "analysisStatus": "pending",
    }
    store.add_memory(body.user_id, memory)
    try:
        summary = llm.chat(
            "用一句话概括这段记忆的核心场景和情感。",
            body.text, temperature=0.5, max_tokens=100,
        )
        memory["analysisStatus"] = "completed"
        memory["summary"] = summary
    except Exception:
        memory["analysisStatus"] = "failed"
    return {"ok": True, "data": memory}


@app.get("/api/postcards")
async def get_postcards(user_id: str = "default") -> dict:
    state = store.get_game_state(user_id)
    return {"ok": True, "data": state["postcards"]}


@app.get("/api/state")
async def get_state(user_id: str = "default") -> dict:
    state = store.get_game_state(user_id)
    return {"ok": True, "data": state}


@app.get("/api/landmarks")
async def get_landmarks(user_id: str = "default") -> dict:
    """查看当前地标库（调试用）"""
    landmarks = store.get_landmarks(user_id)
    used = store.get_used_landmark_ids(user_id)
    unused = store.get_unused_landmarks(user_id)
    return {
        "ok": True,
        "data": {
            "total": len(landmarks),
            "used_count": len(used),
            "used_ids": used,
            "unused_count": len(unused),
            "landmarks": landmarks,
        },
    }


@app.get("/api/image/{postcard_id}")
async def serve_image(postcard_id: str):
    """从本地缓存提供生成的图片"""
    cached = store.get_cached_image(postcard_id)
    if cached:
        image_data, content_type = cached
        return Response(content=image_data, media_type=content_type)
    return Response(content=b"", status_code=404)


@app.post("/api/reset")
async def reset_state(user_id: str = "default") -> dict:
    store._users.pop(user_id, None)
    return {"ok": True, "message": "已重置"}


# ── 静态资源：前端文件挂载到根路径 ──
import os as _os
_frontend_dir = _os.path.join(_os.path.dirname(__file__), "..", "frontend")
if _os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
