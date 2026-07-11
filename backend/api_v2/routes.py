"""API v2 路由 — 全部需要 Bearer Token 认证"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Hometown, Letter, Memory, PastSelfProfile, Postcard, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["v2"])


# ──────────── 请求模型 ────────────

class HometownInitReq(BaseModel):
    province: str = ""
    city: str = ""
    county: str = ""
    hometown_name: str = ""


class LetterSendReq(BaseModel):
    text: str
    place_hint: str = ""
    mood_hint: str = ""


class MemorySaveReq(BaseModel):
    text: str
    tags: list[str] = []
    place_hint: str = ""


# ──────────── 端点 ────────────

@router.get("/state")
async def v2_get_state(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取完整游戏状态"""
    # Hometown
    result = await db.execute(select(Hometown).where(Hometown.user_id == user.id))
    h = result.scalar_one_or_none()
    hometown = {
        "province": h.province if h else "",
        "city": h.city if h else "",
        "county": h.county if h else "",
        "hometownName": h.hometown_name if h else "",
    }

    # Postcards
    result = await db.execute(
        select(Postcard)
        .where(Postcard.user_id == user.id)
        .order_by(Postcard.created_at.desc())
        .limit(100)
    )
    postcards = []
    for pc in result.scalars().all():
        image_url = ""
        if pc.image_path:
            image_url = f"http://127.0.0.1:8787/api/v2/image/{pc.image_path}"
        postcards.append({
            "id": str(pc.id),
            "title": pc.title,
            "body": pc.body,
            "poem": pc.poem,
            "place": pc.place,
            "landmarkId": pc.landmark_id,
            "landmarkDescription": pc.landmark_description,
            "mood": pc.mood,
            "imageUrl": image_url,
            "imagePrompt": pc.image_prompt,
            "searchImageUrls": pc.search_image_urls,
            "createdAt": pc.created_at.isoformat() if pc.created_at else "",
            "letterText": pc.letter_text,
            "tags": pc.tags,
            "usedFallback": pc.used_fallback,
        })

    # Letters
    result = await db.execute(
        select(Letter)
        .where(Letter.user_id == user.id)
        .order_by(Letter.timestamp.desc())
        .limit(20)
    )
    letters = []
    for lt in result.scalars().all():
        letters.append({
            "id": f"ltr-{lt.id}",
            "text": lt.text,
            "place": lt.place,
            "mood": lt.mood,
            "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
        })

    # Memories
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == user.id)
        .order_by(Memory.timestamp.desc())
        .limit(40)
    )
    memories = []
    for mem in result.scalars().all():
        memories.append({
            "id": f"mem-{mem.id}",
            "text": mem.text,
            "tags": mem.tags,
            "placeHint": mem.place_hint,
            "timestamp": mem.timestamp.isoformat() if mem.timestamp else "",
            "analysisStatus": mem.analysis_status,
            "summary": mem.summary,
        })

    # Past self profile
    result = await db.execute(
        select(PastSelfProfile).where(PastSelfProfile.user_id == user.id)
    )
    psp = result.scalar_one_or_none()
    past_self = {}
    if psp:
        past_self = {
            "summary": psp.summary,
            "latent_place_affinities": psp.latent_place_affinities,
            "sensory_biases": psp.sensory_biases,
            "identity_signals": psp.identity_signals,
            "recent_memory_signals": psp.recent_memory_signals,
        }

    # Landmarks
    from services.landmark_service_v2 import get_user_landmarks
    landmarks = await get_user_landmarks(db, user.id)

    return {
        "ok": True,
        "data": {
            "current_day": user.current_day,
            "hometown": hometown,
            "profile": {"hometownName": hometown.get("hometownName", "")},
            "letters": letters,
            "memories": memories,
            "postcards": postcards,
            "past_self_profile": past_self,
            "landmarks": landmarks,
        },
    }


@router.post("/hometown/init")
async def v2_init_hometown(
    body: HometownInitReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """初始化/更新故乡"""
    result = await db.execute(select(Hometown).where(Hometown.user_id == user.id))
    h = result.scalar_one_or_none()

    if h:
        h.province = body.province
        h.city = body.city
        h.county = body.county
        h.hometown_name = body.hometown_name or f"{body.province}{body.city}{body.county}"
    else:
        h = Hometown(
            user_id=user.id,
            province=body.province,
            city=body.city,
            county=body.county,
            hometown_name=body.hometown_name or f"{body.province}{body.city}{body.county}",
        )
        db.add(h)

    await db.flush()

    # 播种地标
    from services.llm_service import LlmService
    from services.search_service import SearchService
    from services.pipeline_service import LetterPipeline
    # We need the pipeline's _search_landmark_context — use a simple approach
    search_ctx = ""
    try:
        _search = SearchService()
        queries = [
            f"{body.city} 地标建筑 景点",
            f"{body.city} 旅游景点 推荐",
        ]
        if body.county:
            queries.append(f"{body.county} 地标 日常 老街")
        results = []
        for q in queries[:2]:
            try:
                items = await _search.search_text(q, num=3)
                for item in items[:2]:
                    t = item.get("content", "").strip()
                    if t and len(t) > 10:
                        results.append(f"[{q}] {t[:120]}")
            except Exception:
                pass
        search_ctx = "\n".join(results[:8]) if results else ""
    except Exception:
        pass

    from services.landmark_service_v2 import ensure_landmarks
    await ensure_landmarks(
        db, user.id,
        {"province": body.province, "city": body.city, "county": body.county,
         "hometownName": body.hometown_name or f"{body.province}{body.city}{body.county}"},
        None, None, search_ctx,
    )

    hometown_dict = {
        "province": h.province, "city": h.city,
        "county": h.county, "hometownName": h.hometown_name,
    }
    return {
        "ok": True,
        "data": {
            "hometown": hometown_dict,
            "profile": {"hometownName": h.hometown_name or ""},
        },
    }


@router.post("/letter/send")
async def v2_send_letter(
    body: LetterSendReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发信核心流程"""
    from services.llm_service import LlmService
    from services.search_service import SearchService
    from services.image_service import ImageService
    from services.landmark_service import LandmarkService as OldLandmarkService
    from services.selection_service import SelectionService
    from services.poem_service import PoemService
    from services.pipeline_service import LetterPipeline

    llm = LlmService()
    search = SearchService()
    image_gen = ImageService()
    landmark_svc_old = OldLandmarkService(llm)
    selection_svc = SelectionService(llm)
    poem_svc = PoemService(llm)

    pipeline = LetterPipeline(
        llm=llm,
        search=search,
        image_gen=image_gen,
        landmark_svc=landmark_svc_old,
        selection_svc=selection_svc,
        poem_svc=poem_svc,
    )

    return await pipeline.process(
        db=db,
        user=user,
        text=body.text,
        place_hint=body.place_hint,
        mood_hint=body.mood_hint,
    )


@router.post("/memory/save")
async def v2_save_memory(
    body: MemorySaveReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存记忆"""
    from services.llm_service import LlmService

    memory = Memory(
        user_id=user.id,
        text=body.text,
        tags=body.tags,
        place_hint=body.place_hint,
        timestamp=datetime.now(timezone.utc),
        analysis_status="pending",
    )
    db.add(memory)
    await db.flush()

    try:
        llm = LlmService()
        summary = llm.chat(
            "用一句话概括这段记忆的核心场景和情感。",
            body.text, temperature=0.5, max_tokens=100,
        )
        memory.analysis_status = "completed"
        memory.summary = summary
    except Exception:
        memory.analysis_status = "failed"

    await db.flush()

    return {
        "ok": True,
        "data": {
            "id": f"mem-{memory.id}",
            "text": memory.text,
            "tags": memory.tags,
            "placeHint": memory.place_hint,
            "timestamp": memory.timestamp.isoformat(),
            "analysisStatus": memory.analysis_status,
            "summary": memory.summary,
        },
    }


@router.get("/postcards")
async def v2_get_postcards(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Postcard)
        .where(Postcard.user_id == user.id)
        .order_by(Postcard.created_at.desc())
    )
    postcards = []
    for pc in result.scalars().all():
        image_url = ""
        if pc.image_path:
            image_url = f"http://127.0.0.1:8787/api/v2/image/{pc.image_path}"
        postcards.append({
            "id": str(pc.id),
            "title": pc.title,
            "body": pc.body,
            "poem": pc.poem,
            "place": pc.place,
            "landmarkId": pc.landmark_id,
            "landmarkDescription": pc.landmark_description,
            "mood": pc.mood,
            "imageUrl": image_url,
            "imagePrompt": pc.image_prompt,
            "searchImageUrls": pc.search_image_urls,
            "createdAt": pc.created_at.isoformat() if pc.created_at else "",
            "letterText": pc.letter_text,
            "tags": pc.tags,
            "usedFallback": pc.used_fallback,
        })
    return {"ok": True, "data": postcards}


@router.get("/landmarks")
async def v2_get_landmarks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.landmark_service_v2 import get_user_landmarks, get_unused_landmarks
    all_lm = await get_user_landmarks(db, user.id)
    unused = await get_unused_landmarks(db, user.id)
    used = [lm for lm in all_lm if lm.get("is_used")]
    return {
        "ok": True,
        "data": {
            "total": len(all_lm),
            "used_count": len(used),
            "used_ids": [lm["id"] for lm in used],
            "unused_count": len(unused),
            "landmarks": all_lm,
        },
    }


@router.get("/image/{image_id}")
async def v2_serve_image(image_id: str):
    """从文件系统提供图片"""
    from services.image_storage import read_image
    data = await read_image(image_id)
    if data:
        img_bytes, content_type = data
        return Response(content=img_bytes, media_type=content_type)
    return Response(content=b"", status_code=404)
