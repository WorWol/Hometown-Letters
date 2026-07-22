from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Hometown, Letter, LetterLike, Memory, PastSelfProfile, Postcard, User
from services.style_service import get_user_image_style
from .common import postcard_dict

router = APIRouter(tags=["state"])


@router.get("/state")
async def get_state(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    hometown_row = await db.scalar(select(Hometown).where(Hometown.user_id == user.id))
    hometown = {
        "province": hometown_row.province if hometown_row else "",
        "city": hometown_row.city if hometown_row else "",
        "county": hometown_row.county if hometown_row else "",
        "hometownName": hometown_row.hometown_name if hometown_row else "",
    }

    postcards = [
        postcard_dict(row)
        for row in (await db.scalars(
            select(Postcard).where(Postcard.user_id == user.id)
            .order_by(Postcard.created_at.desc()).limit(100)
        )).all()
    ]
    letters = [
        {
            "id": f"ltr-{row.id}", "text": row.text, "place": row.place,
            "mood": row.mood, "timestamp": row.timestamp.isoformat() if row.timestamp else "",
        }
        for row in (await db.scalars(
            select(Letter).where(Letter.user_id == user.id)
            .order_by(Letter.timestamp.desc()).limit(20)
        )).all()
    ]
    memories = [
        {
            "id": f"mem-{row.id}", "text": row.text, "tags": row.tags,
            "placeHint": row.place_hint, "timestamp": row.timestamp.isoformat() if row.timestamp else "",
            "analysisStatus": row.analysis_status, "summary": row.summary,
        }
        for row in (await db.scalars(
            select(Memory).where(Memory.user_id == user.id)
            .order_by(Memory.timestamp.desc()).limit(40)
        )).all()
    ]

    image_style = await get_user_image_style(db, user.id)

    profile = await db.scalar(select(PastSelfProfile).where(PastSelfProfile.user_id == user.id))
    past_self = {
        "summary": profile.summary,
        "latent_place_affinities": profile.latent_place_affinities,
        "sensory_biases": profile.sensory_biases,
        "identity_signals": profile.identity_signals,
        "recent_memory_signals": profile.recent_memory_signals,
    } if profile else {}

    liked_result = await db.execute(
        select(LetterLike, Letter, Postcard, User, Hometown)
        .join(Letter, LetterLike.letter_id == Letter.id)
        .outerjoin(Postcard, and_(Postcard.user_id == Letter.user_id, Postcard.letter_text == Letter.text))
        .join(User, Letter.user_id == User.id)
        .outerjoin(Hometown, Hometown.user_id == User.id)
        .where(LetterLike.user_id == user.id)
        .order_by(LetterLike.created_at.desc()).limit(20)
    )
    liked_items = []
    for _, letter, postcard, author, author_hometown in liked_result.all():
        item = {
            "id": f"ltr-{letter.id}", "text": letter.text, "place": letter.place or "",
            "mood": letter.mood or "", "timestamp": letter.timestamp.isoformat() if letter.timestamp else "",
            "author": {"username": author.username, "hometown": (author_hometown.hometown_name or author_hometown.city or "") if author_hometown else ""},
        }
        if postcard:
            item["postcard"] = postcard_dict(postcard)
        liked_items.append(item)

    return {"ok": True, "data": {
        "current_day": user.current_day, "postcard_limit": user.postcard_limit,
        "postcard_count": user.postcard_count, "hometown": hometown,
        "profile": {"hometownName": hometown["hometownName"]}, "letters": letters,
        "memories": memories, "postcards": postcards, "past_self_profile": past_self,
        "likedItems": liked_items,
        "imageStyle": image_style,
    }}
