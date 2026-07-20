from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Hometown, Letter, LetterLike, Postcard, User
from .common import postcard_dict

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/feed")
async def get_community_feed(limit: int = 10, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Letter, Postcard, User, Hometown)
        .outerjoin(Postcard, and_(Postcard.user_id == Letter.user_id, Postcard.letter_text == Letter.text))
        .join(User, Letter.user_id == User.id)
        .outerjoin(Hometown, Hometown.user_id == User.id)
        .where(Letter.user_id != user.id)
        .order_by(func.random())
        .limit(max(1, min(limit, 30)))
    )).all()
    liked_ids = {row[0] for row in (await db.execute(select(LetterLike.letter_id).where(LetterLike.user_id == user.id))).all()}
    items = []
    for letter, postcard, author, hometown in rows:
        item = {"id": f"ltr-{letter.id}", "text": letter.text, "place": letter.place or "", "mood": letter.mood or "", "timestamp": letter.timestamp.isoformat() if letter.timestamp else "", "author": {"username": author.username, "hometown": (hometown.hometown_name or hometown.city or "") if hometown else ""}, "liked": letter.id in liked_ids}
        if postcard:
            item["postcard"] = postcard_dict(postcard)
        items.append(item)
    return {"ok": True, "data": {"items": items}}


@router.post("/like/{letter_id}")
async def like_community_letter(letter_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(Letter.id).where(Letter.id == letter_id, Letter.user_id != user.id)) is None:
        return {"ok": False, "error": "信件不存在"}
    if await db.scalar(select(LetterLike).where(LetterLike.user_id == user.id, LetterLike.letter_id == letter_id)) is None:
        db.add(LetterLike(user_id=user.id, letter_id=letter_id))
        await db.flush()
    return {"ok": True, "data": {"liked": True}}


@router.delete("/like/{letter_id}")
async def unlike_community_letter(letter_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(LetterLike).where(LetterLike.user_id == user.id, LetterLike.letter_id == letter_id))
    if existing:
        await db.delete(existing)
        await db.flush()
    return {"ok": True, "data": {"liked": False}}
