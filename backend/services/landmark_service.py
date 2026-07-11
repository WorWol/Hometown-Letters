"""地标库服务 — DB 存储 + LLM/搜索生成（统一版）

地标分两个层级：
  - tier="city"   市级地标：全市范围的大标志性建筑/旅游景点
  - tier="county" 区县级地标：具体区县的小记忆点/生活场景

生成策略：LLM + 联网搜索（主）→ 硬编码种子（fallback）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Landmark

logger = logging.getLogger("hometown")

# ── 硬编码种子（当 LLM 不可用时的 fallback）──
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

# ── LLM System prompts ──
SYSTEM_SEED_LANDMARKS = """你是一位熟悉中国地标的乡土专家。

下面是从网络搜索到的该地区真实地标信息（搜索结果）。
请根据这些搜索结果，结合你的知识，整理出两个层级的地标：

## 第一层：市级地标（全市范围的大标志性建筑/旅游景点）
- 整个地级市范围内最有名的 5 个地标
- 旅游景点、历史建筑、城市名片级别

## 第二层：区县级地标（具体区县的小记忆点/生活场景）
- 该区县特有的 5 个小场景
- 本地人日常会去的地方：公园、学校、菜市场、老街、散步道

场景类型 (scene_type)：lakeside_dam, bridge_roadside, school_gate, street_food, path_to_pond, park, market, temple, mountain, other

返回纯 JSON 数组（10个），不要 markdown，不要多余文字：
[
  {"name": "东江湖", "description": "著名湖泊景区，雾漫小东江的摄影胜地", "scene_type": "lakeside_dam", "tier": "city"},
  {"name": "秀流公园", "description": "市区老公园，承载几代人记忆，晚上很多人散步", "scene_type": "park", "tier": "county"}
]

city 在前 5 个，county 在后 5 个。""" + " 参考搜索结果中的真实地名，不要凭空编造。"


SYSTEM_SUPPLEMENT_LANDMARKS = """用户的地标库已经循环用完一轮了。
下面是网络搜索到的该地区真实地标信息。

请从搜索结果中挑选与已有地标不重复的 2-4 个新地标补充进去。
同样分两个层级：
- tier="city"（市级大标志建筑/旅游景点）
- tier="county"（区县小记忆点/生活场景）

纯 JSON 数组，不要 markdown。""" + " 优先从搜索结果的真实名称中选取。"


# ── 公共 API（模块级 async 函数）──

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


async def mark_landmark_used(db: AsyncSession, user_id: int, landmark_id: int, current_day: int) -> None:
    lm = await db.get(Landmark, landmark_id)
    if lm and lm.user_id == user_id:
        lm.is_used = True
        lm.used_count = (lm.used_count or 0) + 1
        lm.last_used_day = current_day


async def ensure_landmarks(
    db: AsyncSession,
    user_id: int,
    hometown: dict,
    llm_service,
    search_service=None,
    search_ctx: str = "",
) -> list[dict]:
    """确保地标库存在。优先 LLM+搜索生成，fallback 硬编码种子。"""
    existing = await get_user_landmarks(db, user_id)
    if existing:
        return existing

    # 尝试 LLM 生成（需要搜索上下文）
    if llm_service and search_ctx.strip():
        try:
            return await _seed_via_llm(db, user_id, hometown, llm_service, search_ctx)
        except Exception as e:
            logger.warning("LLM seed failed: %s, falling back to basic seeds", e)

    # Fallback: 硬编码种子
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
    search_service=None,
    search_ctx: str = "",
) -> None:
    """用完则重置（循环复用），有搜索上下文时尝试补充新地标"""
    unused = await get_unused_landmarks(db, user_id)
    if unused:
        return

    # 重置所有地标的 is_used
    await db.execute(
        update(Landmark)
        .where(Landmark.user_id == user_id)
        .values(is_used=False)
    )
    await db.flush()

    # 有搜索上下文时尝试补充
    if llm_service and search_ctx.strip():
        try:
            await _supplement_via_llm(db, user_id, llm_service, search_ctx)
        except Exception as e:
            logger.warning("LLM supplement failed: %s", e)


async def get_next_landmark(
    db: AsyncSession,
    user_id: int,
    letter_text: str = "",
    place_hint: str = "",
    llm_service=None,
) -> dict | None:
    """获取下一个地标 — 地点提示匹配 > LLM 内容匹配 > 层级交替"""
    unused = await get_unused_landmarks(db, user_id)
    if not unused:
        return None

    # 1. 精确地点提示匹配
    if place_hint.strip():
        hint_clean = place_hint.strip()
        exact_matches = []
        partial_matches = []
        fuzzy_matches = []

        for lm in unused:
            name = lm.get("name", "")
            desc = lm.get("description", "")
            if hint_clean in name:
                exact_matches.append(lm)
            elif hint_clean in f"{name} {desc}":
                partial_matches.append(lm)
            else:
                lhs = set(hint_clean)
                rhs = set(name)
                if lhs and rhs:
                    overlap = len(lhs & rhs) / max(len(lhs), len(rhs))
                    if overlap >= 0.5:
                        fuzzy_matches.append((overlap, lm))

        if exact_matches:
            logger.info("place_hint exact match: %s → %s", place_hint, exact_matches[0]["name"])
            return exact_matches[0]
        if partial_matches:
            logger.info("place_hint partial match: %s → %s", place_hint, partial_matches[0]["name"])
            return partial_matches[0]
        if fuzzy_matches:
            fuzzy_matches.sort(key=lambda x: x[0], reverse=True)
            best = fuzzy_matches[0][1]
            logger.info("place_hint fuzzy match: %s → %s (score=%.2f)", place_hint, best["name"], fuzzy_matches[0][0])
            return best

        # 没匹配到 → 插入自定义地标
        logger.info("place_hint '%s' not found, creating custom landmark", place_hint)
        now = datetime.now(timezone.utc)
        custom_lm = Landmark(
            user_id=user_id,
            name=hint_clean,
            description=f"用户指定的地点：{hint_clean}",
            scene_type="bridge_roadside",
            tier="county",
            used_count=0,
            last_used_day=None,
            source="user_place_hint",
            is_used=False,
            created_at=now,
        )
        db.add(custom_lm)
        await db.flush()
        return _lm_to_dict(custom_lm)

    # 2. LLM 内容匹配
    if letter_text.strip() and len(unused) > 1 and llm_service:
        chosen = _select_best_landmark(unused, letter_text, llm_service)
        if chosen:
            logger.info("LLM selected landmark from %d unused: %s", len(unused), chosen.get("name"))
            return chosen

    # 3. 层级交替
    city_lms = [lm for lm in unused if lm.get("tier") == "city"]
    county_lms = [lm for lm in unused if lm.get("tier") == "county"]
    total = await _count_all_landmarks(db, user_id)

    if total % 2 == 0 and city_lms:
        return city_lms[0]
    if county_lms:
        return county_lms[0]
    if city_lms:
        return city_lms[0]
    return unused[0]


# ── 内部辅助 ──

async def _seed_via_llm(
    db: AsyncSession, user_id: int, hometown: dict, llm_service, search_ctx: str
) -> list[dict]:
    """LLM + 搜索生成地标"""
    hometown_str = (
        f"地级市：{hometown.get('city', '')}\n"
        f"下辖区县：{hometown.get('county', '')}\n"
        f"省：{hometown.get('province', '')}\n"
        f"名称：{hometown.get('hometownName', '')}"
    ).strip()

    user_msg = f"地区信息：\n{hometown_str}"
    if search_ctx:
        user_msg += f"\n\n网络搜索结果（请参考）：\n{search_ctx[:1200]}"
    user_msg += "\n\n请生成该地区两个层级的地标（共10个）。"

    raw = llm_service.chat(
        SYSTEM_SEED_LANDMARKS,
        user_msg,
        temperature=0.7,
        max_tokens=1200,
    )
    landmarks = _parse_landmarks(raw)

    if not landmarks:
        raise ValueError("LLM returned empty landmarks")

    now = datetime.now(timezone.utc)
    for lm in landmarks:
        lm.setdefault("tier", "county")
        db.add(Landmark(
            user_id=user_id,
            name=lm["name"],
            description=lm.get("description", ""),
            scene_type=lm.get("scene_type", "other"),
            tier=lm["tier"],
            used_count=0,
            last_used_day=None,
            source="web_search_seed",
            is_used=False,
            created_at=now,
        ))
    await db.flush()
    return await get_user_landmarks(db, user_id)


async def _supplement_via_llm(
    db: AsyncSession, user_id: int, llm_service, search_ctx: str
) -> list[dict]:
    """从搜索结果补充新地标"""
    existing = await get_user_landmarks(db, user_id)
    existing_names = [lm["name"] for lm in existing]

    user_msg = (
        f"已有地标：{'、'.join(existing_names)}\n\n"
        f"网络搜索结果：\n{search_ctx[:1200]}\n\n"
        f"请从搜索结果中挑选 2-4 个与已有地标不重复的补充。"
    )
    raw = llm_service.chat(
        SYSTEM_SUPPLEMENT_LANDMARKS,
        user_msg,
        temperature=0.7,
        max_tokens=800,
    )
    new_data = _parse_landmarks(raw)

    now = datetime.now(timezone.utc)
    for lm in new_data:
        lm.setdefault("tier", "county")
        db.add(Landmark(
            user_id=user_id,
            name=lm["name"],
            description=lm.get("description", ""),
            scene_type=lm.get("scene_type", "other"),
            tier=lm["tier"],
            used_count=0,
            last_used_day=None,
            source="web_search_supplement",
            is_used=False,
            created_at=now,
        ))
    await db.flush()
    return await get_user_landmarks(db, user_id)


def _select_best_landmark(candidates: list[dict], user_context: str, llm_service) -> dict | None:
    """LLM 从候选地标中选最匹配的"""
    if len(candidates) == 1:
        return candidates[0]

    names = [f"{lm['name']}（{lm.get('description', '')}）[{lm.get('scene_type', '')}]"
             for lm in candidates]
    prompt = (
        f"用户输入：{user_context}\n\n"
        f"候选地标：\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
        + "\n\n选最贴切的一个，只输出数字。"
    )
    try:
        raw = llm_service.chat(
            "你是一位故乡地理专家。根据用户描述的情感、地点和场景，从候选地标中选出最贴近的一个。只看名字+描述就够，不要过度分析。只输出数字。",
            prompt, temperature=0.3, max_tokens=10,
        )
        idx = int(raw.strip()) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]
    except (ValueError, IndexError, Exception):
        pass
    return candidates[0]


def _seed_basic_landmarks(user_id: int, hometown: dict) -> list[dict]:
    """硬编码种子（LLM 不可用时的 fallback）"""
    city = hometown.get("city", "")
    county = hometown.get("county", "")
    now = datetime.now(timezone.utc)
    landmarks = []

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


async def _count_all_landmarks(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(Landmark).where(Landmark.user_id == user_id)
    )
    return len(result.scalars().all())


def _parse_landmarks(raw: str) -> list[dict]:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        clean = clean.rsplit("\n", 1)[0]
        if clean.endswith("```"):
            clean = clean[:-3]
    data = json.loads(clean)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "landmarks" in data:
        return data["landmarks"]
    return []


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
        "id": lm_data.get("id", -1),
        "name": lm_data.get("name", ""),
        "description": lm_data.get("description", ""),
        "scene_type": lm_data.get("scene_type", "other"),
        "tier": lm_data.get("tier", "county"),
        "used_count": lm_data.get("used_count", 0),
        "last_used_day": lm_data.get("last_used_day"),
        "source": lm_data.get("source", "seed"),
        "is_used": lm_data.get("is_used", False),
    }
