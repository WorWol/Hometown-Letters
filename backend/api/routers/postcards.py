from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Postcard, SystemEvent, User
from services.data_service import delete_postcard as remove_postcard
from .common import postcard_dict

logger = logging.getLogger(__name__)
router = APIRouter(tags=["postcards"])


@router.get("/postcards")
async def get_postcards(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Postcard).where(Postcard.user_id == user.id).order_by(Postcard.created_at.desc()))).all()
    return {"ok": True, "data": [postcard_dict(row) for row in rows]}


@router.delete("/postcards/{postcard_id}")
async def delete_postcard(postcard_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    postcard = await db.scalar(select(Postcard).where(Postcard.id == postcard_id, Postcard.user_id == user.id))
    if postcard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="明信片不存在")
    try:
        await remove_postcard(db, postcard)
    except Exception as error:
        logger.exception("postcard image deletion failed postcard=%s user=%s", postcard_id, user.id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="图片存储删除失败，明信片未删除") from error
    db.add(SystemEvent(level="info", event_type="postcard_deleted", message="postcard and image objects deleted", user_id=user.id, event_metadata={"postcard_id": postcard_id}))
    await db.flush()
    return {"ok": True, "data": {"id": str(postcard_id)}}
