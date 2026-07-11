"""DB 版地标管理 — 使用 SQLAlchemy ORM"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Landmark

logger = logging.getLogger(__name__)

CITY_SOURCES = [
    {"name": "城市中心", "desc": "市区的核心地带，高楼林立、车水马龙", "scene": "city"},
    {"name": "火车站", "desc": "人来人往的车站，离别与重逢在此交织", "scene": "bridge_roadside"},
    {"name": "图书馆", "desc": "安静的知识殿堂，书架间藏着无数故事", "scene": "other"},
    {"name": "城市公园", "desc": "钢筋森林里的一片绿洲，老人下棋、孩童嬉戏", "scene": "park"},
]
COUNTY_SOURCES = [
    {"name": "小学门口", "desc": "放学的铃声响起，孩子们涌出校门", "scene": "school_gate"},
    {"name": "老街", "desc": "青石板路边的老房子，时光在这里慢了下来", "scene": "street_food"},
    {"name": "菜市场", "desc": "清晨最热闹的地方，吆喝声与讨价声此起彼伏", "scene": "market"},
    {"name": "河边", "desc": "柳树成荫的河岸，水流声中有童年的回声", "scene": "path_to_pond"},
    {"name": "村口", "desc": "进村必经的路口，槐树下总有故事的老人", "scene": "other"},
]


async def get_user_landmarks(db: AsyncSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(Landmark).where(Landmark.user_id == user_id)
    )
    landmarks = result.scalars().all()
    return [_lm_to_dict(lm) for lm in landmarks]


async def get_unused_landmarks(db: AsyncSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(Landmark).where(
            Landmark.user_id == user_id, Landmark.is_used == False
        )
    )
    return [_lm_to_dict(lm) for lm in result.scalars().all()]


async def ensure_landmarks(
    db: AsyncSession,
    user_id: int,
    hometown: dict,
    llm_service,
    search_service,
    search_ctx: str = "",
) -> list[dict]:
    existing = await get_user_landmarks(db, user_id)
    if existing:
        return existing

    seed = _seed_basic_landmarks(user_id, hometown)
    for lm_data in seed:
        lm = Landmark(**lm_data)
        db.add(lm)
    await db.flush()
    return [_lm_to_dict_for_db(lm_data) for lm_data in seed]


async def refresh_if_exhausted(
    db: AsyncSession,
    user_id: int,
    hometown: dict,
    llm_service,
    search_service,
    search_ctx: str = "",
) -> None:
    unused = await get_unused_landmarks(db, user_id)
    if unused:
        return

    # 重置所有地标的 is_used
    from sqlalchemy import update
    await db.execute(
        update(Landmark)
        .where(Landmark.user_id == user_id)
        .values(is_used=False)
    )
    await db.flush()


async def get_next_landmark(
    db: AsyncSession,
    user_id: int,
    letter_text: str = "",
    place_hint: str = "",
    llm_service=None,
) -> dict | None:
    unused = await get_unused_landmarks(db, user_id)
    if not unused:
        return None

    # 地点提示精确匹配
    if place_hint:
        for lm in unused:
            if lm["name"] == place_hint:
                return lm

    # 部分匹配
    if place_hint:
        for lm in unused:
            if place_hint in lm["name"] or lm["name"] in place_hint:
                return lm

    # 交替 selection on tier
    city_lms = [lm for lm in unused if lm.get("tier") == "city"]
    county_lms = [lm for lm in unused if lm.get("tier") == "county"]

    total_landmarks = await _count_all_landmarks(db, user_id)
    if total_landmarks % 2 == 0 and city_lms:
        return city_lms[0]
    if county_lms:
        return county_lms[0]
    if city_lms:
        return city_lms[0]
    return unused[0] if unused else None


async def mark_landmark_used(db: AsyncSession, user_id: int, landmark_id: int, current_day: int) -> None:
    lm = await db.get(Landmark, landmark_id)
    if lm and lm.user_id == user_id:
        lm.is_used = True
        lm.used_count = (lm.used_count or 0) + 1
        lm.last_used_day = current_day


async def _count_all_landmarks(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(Landmark).where(Landmark.user_id == user_id)
    )
    return len(result.scalars().all())


def _seed_basic_landmarks(user_id: int, hometown: dict) -> list[dict]:
    province = hometown.get("province", "")
    city = hometown.get("city", "")
    county = hometown.get("county", "")

    landmarks = []
    now = datetime.now(timezone.utc)

    # City-tier landmarks
    for src in CITY_SOURCES:
        name = f"{city}{src['name']}" if city else src["name"]
        landmarks.append({
            "user_id": user_id,
            "name": name,
            "description": f"{city}{src['name']} — {src['desc']}",
            "scene_type": src["scene"],
            "tier": "city",
            "used_count": 0,
            "last_used_day": None,
            "source": "seed",
            "is_used": False,
            "created_at": now,
        })

    # County-tier landmarks
    for src in COUNTY_SOURCES:
        name = f"{county}{src['name']}" if county else src["name"]
        landmarks.append({
            "user_id": user_id,
            "name": name,
            "description": f"{county}{src['name']} — {src['desc']}",
            "scene_type": src["scene"],
            "tier": "county",
            "used_count": 0,
            "last_used_day": None,
            "source": "seed",
            "is_used": False,
            "created_at": now,
        })

    return landmarks


def _lm_to_dict(lm: Landmark) -> dict:
    return {
        "id": lm.id,
        "name": lm.name,
        "description": lm.description,
        "scene_type": lm.scene_type,
        "tier": lm.tier,
        "used_count": lm.used_count,
        "last_used_day": lm.last_used_day,
        "source": lm.source,
        "is_used": lm.is_used,
    }


def _lm_to_dict_for_db(lm_data: dict) -> dict:
    return {
        "id": -1,  # placeholder, real id from DB
        "name": lm_data.get("name", ""),
        "description": lm_data.get("description", ""),
        "scene_type": lm_data.get("scene_type", "other"),
        "tier": lm_data.get("tier", "county"),
        "used_count": lm_data.get("used_count", 0),
        "last_used_day": lm_data.get("last_used_day"),
        "source": lm_data.get("source", "seed"),
        "is_used": lm_data.get("is_used", False),
    }
