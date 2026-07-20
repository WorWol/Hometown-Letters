from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import SystemEvent, User
from .common import get_pipeline
from services.image_service import ImageService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["letters"])


class LetterSendReq(BaseModel):
    text: str
    place_hint: str = ""
    mood_hint: str = ""


async def _reserve_quota(db: AsyncSession, user: User) -> None:
    reservation = await db.execute(
        update(User).where(User.id == user.id, User.postcard_count < User.postcard_limit)
        .values(postcard_count=User.postcard_count + 1)
    )
    if reservation.rowcount != 1:
        db.add(SystemEvent(level="warning", event_type="postcard_quota_rejected", message="postcard quota exhausted", user_id=user.id, event_metadata={"limit": user.postcard_limit}))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"每位用户最多生成 {user.postcard_limit} 张明信片")
    await db.flush()


async def _run_pipeline(*, db, user, pipeline, text: str, place_hint: str, mood_hint: str, reference_image_data: bytes | None = None):
    await _reserve_quota(db, user)
    try:
        result = await pipeline.process(db=db, user=user, text=text, place_hint=place_hint, mood_hint=mood_hint, reference_image_data=reference_image_data)
        if not result.get("ok"):
            await db.execute(update(User).where(User.id == user.id).values(postcard_count=User.postcard_count - 1))
            db.add(SystemEvent(level="error", event_type="postcard_failed", message=result.get("error", "postcard pipeline failed"), user_id=user.id))
        else:
            db.add(SystemEvent(level="info", event_type="postcard_created", message="postcard created", user_id=user.id, event_metadata={"postcard_id": result.get("data", {}).get("id"), "reference_type": "upload" if reference_image_data else "search"}))
        return result
    except Exception:
        await db.execute(update(User).where(User.id == user.id).values(postcard_count=User.postcard_count - 1))
        raise


@router.post("/letter/send")
async def send_letter(body: LetterSendReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), pipeline=Depends(get_pipeline)):
    return await _run_pipeline(db=db, user=user, pipeline=pipeline, text=body.text, place_hint=body.place_hint, mood_hint=body.mood_hint)


@router.post("/letter/send-with-image")
async def send_letter_with_image(
    text: str = Form(..., min_length=1, max_length=10000),
    place_hint: str = Form(default="", max_length=128),
    mood_hint: str = Form(default="", max_length=64),
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    pipeline=Depends(get_pipeline),
):
    """使用用户上传的图片作为唯一参考图生成明信片。"""
    data = await image.read(ImageService.MAX_REFERENCE_IMAGE_BYTES + 1)
    valid, reason = ImageService.validate_reference_image(data)
    if not valid:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=reason)
    return await _run_pipeline(db=db, user=user, pipeline=pipeline, text=text, place_hint=place_hint, mood_hint=mood_hint, reference_image_data=data)


@router.get("/community-letters")
async def get_community_letters(limit: int = 5, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    from db.models import Hometown, Letter
    my_count = await db.scalar(select(func.count(Letter.id)).where(Letter.user_id == user.id)) or 0
    rows = (await db.execute(
        select(Letter, Hometown).join(Hometown, Letter.user_id == Hometown.user_id, isouter=True)
        .where(Letter.user_id != user.id).order_by(Letter.timestamp.desc()).limit(max(1, min(limit, 20)))
    )).all()
    letters = [{
        "id": f"ltr-{letter.id}", "text": letter.text, "place": letter.place or "", "mood": letter.mood or "",
        "timestamp": letter.timestamp.isoformat() if letter.timestamp else "",
        "hometown": {"province": hometown.province if hometown else "", "city": hometown.city if hometown else "", "hometownName": hometown.hometown_name if hometown else ""} if hometown else None,
    } for letter, hometown in rows]
    return {"ok": True, "data": {"letters": letters, "myLetterCount": my_count}}
