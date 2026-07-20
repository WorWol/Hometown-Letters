from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Hometown, User

router = APIRouter(tags=["profile"])


class HometownInitReq(BaseModel):
    province: str = ""
    city: str = ""
    county: str = ""
    hometown_name: str = ""


@router.post("/hometown/init")
async def init_hometown(body: HometownInitReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    hometown = await db.scalar(select(Hometown).where(Hometown.user_id == user.id))
    name = body.hometown_name or f"{body.province}{body.city}{body.county}"
    if hometown is None:
        hometown = Hometown(user_id=user.id)
        db.add(hometown)
    hometown.province = body.province
    hometown.city = body.city
    hometown.county = body.county
    hometown.hometown_name = name
    await db.flush()
    data = {"province": hometown.province, "city": hometown.city, "county": hometown.county, "hometownName": hometown.hometown_name}
    return {"ok": True, "data": {"hometown": data, "profile": {"hometownName": hometown.hometown_name or ""}}}
