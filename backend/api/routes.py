"""API 路由 — 全部需要 Bearer Token 认证，通过 DI 注入服务"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Hometown, Letter, Memory, PastSelfProfile, Postcard, User
from services import image_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


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


# ──────────── DI 依赖 ────────────

def get_llm(request: Request):
    return request.app.state.llm


def get_search(request: Request):
    return request.app.state.search


def get_pipeline(request: Request):
    return request.app.state.pipeline


# ──────────── 端点 ────────────

@router.get("/state")
async def get_state(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取完整游戏状态"""
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
            image_url = image_storage.get_image_url(pc.image_path)
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
        },
    }


@router.post("/hometown/init")
async def init_hometown(
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
async def send_letter(
    body: LetterSendReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pipeline=Depends(get_pipeline),
):
    """发信核心流程"""
    return await pipeline.process(
        db=db,
        user=user,
        text=body.text,
        place_hint=body.place_hint,
        mood_hint=body.mood_hint,
    )


@router.post("/memory/save")
async def save_memory(
    body: MemorySaveReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_llm),
):
    """保存记忆"""
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
async def get_postcards(
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
            image_url = image_storage.get_image_url(pc.image_path)
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


@router.get("/community-letters")
async def get_community_letters(
    limit: int = 5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取其他用户的公开信件，供新用户作为写作灵感参考。

    前端通过 limit 参数控制获取数量。
    返回其他用户最近写过的信（含故乡省市信息），排除当前用户自己的信。
    """
    from sqlalchemy import func as sa_func

    # 先查当前用户的总信件数
    total_result = await db.execute(
        select(sa_func.count(Letter.id)).where(Letter.user_id == user.id)
    )
    my_count = total_result.scalar() or 0

    # 查其他用户的最近信件，联表 hometown 获取地理位置
    result = await db.execute(
        select(Letter, Hometown)
        .join(Hometown, Letter.user_id == Hometown.user_id, isouter=True)
        .where(Letter.user_id != user.id)
        .order_by(Letter.timestamp.desc())
        .limit(max(1, min(limit, 20)))
    )
    rows = result.all()

    letters = []
    for lt, ht in rows:
        letters.append({
            "id": f"ltr-{lt.id}",
            "text": lt.text,
            "place": lt.place or "",
            "mood": lt.mood or "",
            "timestamp": lt.timestamp.isoformat() if lt.timestamp else "",
            "hometown": {
                "province": ht.province if ht else "",
                "city": ht.city if ht else "",
                "hometownName": ht.hometown_name if ht else "",
            } if ht else None,
        })

    return {
        "ok": True,
        "data": {
            "letters": letters,
            "myLetterCount": my_count,
        },
    }


@router.get("/image/{image_id}")
async def serve_image(image_id: str):
    """从文件系统提供图片"""
    data = await image_storage.read_image(image_id)
    if data:
        img_bytes, content_type = data
        return Response(content=img_bytes, media_type=content_type)
    return Response(content=b"", status_code=404)
