"""图像风格注册表，DB 驱动 + 内存缓存。

风格存储在 image_styles 表，启动时 load_cache() 加载到内存，admin 修改后
reload_cache() 刷新。STYLES 常量仅作为迁移种子源和缓存未加载时的回退，
保证启动早期与单元测试在未初始化数据库时仍可用。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import async_session
from db.models import ImageStyle, Profile

logger = logging.getLogger(__name__)

# ── 内置风格（迁移种子源 + 缓存未加载时的回退） ──
# 每个风格包含：
# - id: 唯一标识
# - label: 前端显示名称
# - style_prompt: 追加到图像生成 prompt 末尾的风格描述（中文）
# - analysis_hint: 注入信件分析 prompt 的 {STYLE_HINT} 占位符的风格名称（中文）

STYLES: list[dict[str, str]] = [
    {
        "id": "pixel_16bit",
        "label": "16位像素风",
        "style_prompt": "16位复古像素画，SNES/GBA时代游戏截图质感，可见像素网格与锐利方块边缘，平涂2D着色，低色彩数怀旧暖色调色板，dithering抖动过渡，CPS2/Neo Geo美学",
        "analysis_hint": "复古16位像素风",
    },
    {
        "id": "watercolor",
        "label": "水彩风",
        "style_prompt": "柔和水彩画，细腻晕染与洇边，可见纸张纹理，透明色层叠加，柔和渐变，手绘插画质感，暖色怀旧调",
        "analysis_hint": "柔和水彩画",
    },
    {
        "id": "ghibli",
        "label": "吉卜力风",
        "style_prompt": "吉卜力风格动漫插画，温暖手绘背景，柔和自然光，繁茂细致景色，赛璐璐角色，怀旧温柔氛围，绘画质感",
        "analysis_hint": "吉卜力风格动漫插画",
    },
    {
        "id": "ink_wash",
        "label": "水墨风",
        "style_prompt": "传统中国水墨画，写意水墨，单色墨韵渐变带细微暖色点缀，写意笔触，宣纸纹理，大量留白",
        "analysis_hint": "传统中国水墨画",
    },
    {
        "id": "retro_photo",
        "label": "复古胶片",
        "style_prompt": "复古胶片照片，暖色褪色，细微颗粒与漏光，柔焦，90年代快照质感，自然光",
        "analysis_hint": "复古胶片照片",
    },
]

DEFAULT_STYLE_ID = "pixel_16bit"

_STYLE_MAP: dict[str, dict[str, str]] = {s["id"]: s for s in STYLES}

# ── 风格负面词（代码常量，与 style_prompt 正向描述配合，送给生图模型 negative_prompt）──
_STYLE_NEGATIVES: dict[str, str] = {
    "pixel_16bit": "平滑渐变, 抗锯齿, 写实细节, 3D渲染, 照片级, 矢量, 高清插画风, 水印, 文字, 签名, logo, 模糊, 低质量",
    "watercolor": "像素边缘, 锐利线条, 3D渲染, 写实, 鲜艳饱和色, 水印, 文字, 签名, logo, 模糊, 低质量",
    "ghibli": "3D渲染, 写实, 像素画, 水印, 文字, 签名, logo, 模糊, 低质量, 多余角色",
    "ink_wash": "3D渲染, 写实, 像素画, 鲜艳饱和色, 水印, 文字, 签名, logo, 模糊",
    "retro_photo": "像素画, 插画, 3D渲染, 水印, 文字, 签名, logo, 过曝, 模糊, 低质量",
}
_DEFAULT_NEGATIVE = "水印, 文字, 签名, logo, 模糊, 低质量, 多余角色, 变形"


def get_style_negative(style_id: str | None) -> str:
    """返回风格的负面提示词（送给生图模型 negative_prompt）。未知风格回退通用负面词。"""
    if style_id and style_id in _STYLE_NEGATIVES:
        return _STYLE_NEGATIVES[style_id]
    return _DEFAULT_NEGATIVE


# ── 内存缓存 ──
# 按 style_id 索引，值为含 id/label/style_prompt/analysis_hint 的 dict。
# 仅缓存 is_active=True 的风格，按 sort_order 升序。
_cache: dict[str, dict[str, str]] = {}
_loaded: bool = False


async def load_cache(db: AsyncSession | None = None) -> None:
    """从数据库加载所有启用的风格到内存缓存。启动时调用。"""
    global _loaded
    if db is not None:
        await _do_load(db)
    else:
        async with async_session() as session:
            await _do_load(session)
    _loaded = True


async def _do_load(db: AsyncSession) -> None:
    rows = (await db.execute(
        select(ImageStyle).where(ImageStyle.is_active.is_(True)).order_by(ImageStyle.sort_order.asc())
    )).scalars().all()
    _cache.clear()
    for row in rows:
        _cache[row.style_id] = {
            "id": row.style_id,
            "label": row.label,
            "style_prompt": row.style_prompt,
            "analysis_hint": row.analysis_hint,
        }
    logger.info("图像风格缓存已加载：%d 项", len(_cache))


async def reload_cache() -> None:
    """admin 增删改风格后刷新缓存。"""
    await load_cache()


def _lookup(style_id: str | None) -> dict[str, str]:
    """按 id 查找风格。

    缓存已加载时以 DB 为唯一真相（找不到回退默认）；缓存未加载时回退硬编码常量。
    """
    if _loaded:
        if style_id and style_id in _cache:
            return _cache[style_id]
        return _cache.get(DEFAULT_STYLE_ID) or _STYLE_MAP[DEFAULT_STYLE_ID]
    if style_id and style_id in _STYLE_MAP:
        return _STYLE_MAP[style_id]
    return _STYLE_MAP[DEFAULT_STYLE_ID]


def list_styles() -> list[dict[str, str]]:
    """返回所有可用风格（不含 style_prompt 细节，供前端展示）。"""
    if _loaded:
        return [{"id": s["id"], "label": s["label"]} for s in _cache.values()]
    return [{"id": s["id"], "label": s["label"]} for s in STYLES]


def get_style(style_id: str | None) -> dict[str, str]:
    """按 id 查找风格，找不到时回退到默认风格。"""
    return _lookup(style_id)


def get_style_prompt(style_id: str | None) -> str:
    """返回风格的 style_prompt（追加到图像 prompt 末尾）。"""
    return _lookup(style_id)["style_prompt"]


def get_analysis_hint(style_id: str | None) -> str:
    """返回风格的 analysis_hint（注入信件分析 prompt）。"""
    return _lookup(style_id)["analysis_hint"]


async def get_user_image_style(db, user_id: int) -> str | None:
    """从 Profile.data 读取用户选择的图像风格，未设置时返回 None。"""
    profile = await db.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile and isinstance(profile.data, dict):
        return profile.data.get("image_style")
    return None
