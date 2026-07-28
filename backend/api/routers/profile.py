from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Hometown, Profile, User
from services.style_service import DEFAULT_STYLE_ID, list_styles

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


class ImageStyleReq(BaseModel):
    style_id: str


@router.get("/image-styles")
async def get_image_styles(user: User = Depends(get_current_user)):
    return {"ok": True, "data": {"styles": list_styles(), "defaultStyleId": DEFAULT_STYLE_ID}}


@router.post("/profile/image-style")
async def set_image_style(body: ImageStyleReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    valid_ids = {s["id"] for s in list_styles()}
    if body.style_id not in valid_ids:
        raise HTTPException(status_code=422, detail="不支持的风格")
    profile = await db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        profile = Profile(user_id=user.id, data={})
        db.add(profile)
    current_data = profile.data if isinstance(profile.data, dict) else {}
    profile.data = {**current_data, "image_style": body.style_id}
    await db.flush()
    return {"ok": True, "data": {"imageStyle": body.style_id}}


class OnboardingReq(BaseModel):
    version: int = Field(ge=1, le=1000)


@router.post("/profile/onboarding")
async def set_onboarding_version(
    body: OnboardingReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        profile = Profile(user_id=user.id, data={})
        db.add(profile)
    current_data = profile.data if isinstance(profile.data, dict) else {}
    profile.data = {**current_data, "onboarding_version": body.version}
    await db.flush()
    return {"ok": True, "data": {"onboardingVersion": body.version}}
