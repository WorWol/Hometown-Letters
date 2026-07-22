"""LLM 提示词注册表与可编辑覆盖。

- 默认提示词定义在 PROMPT_DEFAULTS 中（从各 service 模块迁移而来）。
- 开发者后台可通过 DB 覆盖任意提示词；覆盖内容缓存在内存中，get_prompt() 同步读取。
- 启动时调用 load_cache() 加载所有覆盖；admin 端点调用 set_override/reset_override 同步更新 DB 和缓存。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import async_session
from db.models import PromptOverride

logger = logging.getLogger(__name__)

# ── 默认提示词 ──
# letter_analysis 中的 {STYLE_HINT} 占位符在运行时被替换为用户选择的风格名称。

_LETTER_ANALYSIS_DEFAULT = """你是一位情感细腻的故乡叙事者，善于从只言片语中捕捉画面。

用户写了一封信，信中可能提到了某个地点。请深度分析这封信，提取以下信息：

## 你的任务
1. **visual_themes**：信中提到或隐含的具体视觉元素（建筑、自然景物、光线、颜色、季节、人物活动等），3-8 个，用中文
2. **emotional_tone**：情感基调，如"怀念/温暖/略带感伤"、"兴奋/青春/活力"，用中文短语
3. **scene_type**：最匹配的场景类型，从以下选一个: lakeside_dam, bridge_roadside, school_gate, street_food, path_to_pond, park, market, temple, mountain, city, other
4. **search_keywords**：用于图片搜索的关键词列表（3-5 个），必须包含具体的地理位置上下文。
   - 如果你知道信中地点所在的城市，一定要加上城市名
   - 中文+英文混用，覆盖面更广
   - 例如：如果信中提到"华中科技大学"，你应该写 "武汉 华中科技大学 梧桐 校园"
5. **core_place**：信件中最核心的地点名称。如果用户明确写出了地名就用它；如果信中没提但给了 place_hint 就用 place_hint；如果都没有则用家乡名称
6. **generation_place**：本次 Web Search 和图片生成实际使用的地点。明确地点时用信件地点；没有明确地点时用家乡地址，并补充一个当地代表性景点或生活场景。
7. **image_prompt**：根据前面对信件场景和情感的分析，写一段英文图像生成提示词（50-80词）。必须是 {STYLE_HINT} 风格。
   关键要求：
   - 必须描述具体、可辨识的建筑特征（如红砖教学楼、梧桐树下的石阶、图书馆的拱形窗户）--不能只是泛泛的"校园林荫道"
   - 视角必须是人的平视/仰视角度，能看到建筑正面或侧面的亲切视角，严禁俯视、鸟瞰、远景
   - 只描述视觉元素、光线、氛围、色彩，不要出现具体地名

   好例子："16-bit pixel art of red brick campus buildings with ivy-covered walls seen from ground level, parasol trees framing the view, students sitting on stone steps in golden hour light, warm autumn colors, nostalgic game screenshot aesthetic"

   坏例子（太泛，没特征）："16-bit pixel art of a tree-lined campus avenue at golden hour, students walking"

## 用户画像与历史
如果提供了用户画像和最近写过的信，请注意：
- 如果当前信件和过去的信提到了同一地点或相关场景，保持视觉主题和情感基调的连贯性
- 如果用户画像显示了某种性格特质（如"念旧""安静"），分析时尊重这种特质
- 画像信息仅供参考，不要强行套用--始终以当前信件内容为主

## 注意事项
- 即使用户设的故乡城市和信中提到的地方不同（如故乡是郴州但信提到武汉的大学），你必须以信件中提到的地方为准
- 如果信中只是日常问候而没有具体地点，就根据情感基调推断一个场景
- 搜索关键词中必须包含正确的地理位置
- image_prompt 必须是可直接使用的英文，50-80词，符合指定风格

## 输出格式
纯 JSON，不要 markdown，不要解释：

{
  "visual_themes": ["梧桐树", "教学楼", "黄昏", "学生们"],
  "emotional_tone": "怀念/温暖/略带感伤",
  "scene_type": "school_gate",
  "search_keywords": [
    "武汉 华中科技大学 梧桐 校园",
    "university campus tree-lined path autumn",
    "华中科技大学 教学楼 夕阳"
  ],
    "core_place": "华中科技大学",
    "generation_place": "武汉华中科技大学",
  "image_prompt": "16-bit pixel art of red brick campus buildings with ivy-covered walls seen from ground level, parasol trees framing the view, students sitting on stone steps in golden hour light, warm autumn colors, nostalgic SNES-era game screenshot aesthetic"
}
"""

_POEM_DEFAULT = """你是一位细腻的诗人，写温暖、怀旧、克制的短诗。
诗要像明信片上手写的字迹，4-8行。
不要标题，不要解释，只输出诗歌正文。
"""

_TITLE_DEFAULT = """为一张故乡明信片取一个标题，10字以内，温暖怀旧。
只输出标题本身，不要引号。"""

_BODY_DEFAULT = """以"过去的我"的口吻写一段明信片正文（30-80字）。
温暖、安静、略带怀旧。像是很多年后回看那一天写下的。
只输出正文。"""

_IMAGE_PROMPT_DEFAULT = (
    "You are an expert at writing image generation prompts. "
    "Output only the English prompt, no explanations, no markdown."
)

_BATCH_MEMORY_DEFAULT = """你是一位擅长阅读连续书信的记忆整理者。

下面是同一个用户按时间顺序写下的 5 封信。请基于这 5 封信，产出两层结果：

1. summary_text
- 用 100-180 字中文总结这一阶段用户在想什么、反复提什么、情绪怎样变化
- 聚焦这一阶段，不要上升成终身人格

2. memory
- memory_overview：50-120 字中文，总结这一批记忆的核心线索
- emotion_signals：这一批里反复出现的情绪，每项 {"name": "..."}
- place_signals：这一批反复出现的地点/空间，每项 {"name": "..."}
- theme_signals：这一批反复出现的主题，每项 {"name": "..."}
- people_signals：这一批提到的人物/关系线索，每项 {"name": "..."}
- sensory_signals：这一批明显出现的感官线索，每项 {"name": "..."}

注意：
- 只能根据提供的 5 封信归纳，不能编造
- 没把握时返回空数组
- 输出纯 JSON，不要 markdown，不要解释

输出格式：
{
  "summary_text": "...",
  "memory": {
    "memory_overview": "...",
    "emotion_signals": [{"name": "..."}],
    "place_signals": [{"name": "..."}],
    "theme_signals": [{"name": "..."}],
    "people_signals": [{"name": "..."}],
    "sensory_signals": [{"name": "..."}]
  }
}
"""

_PROFILE_DEFAULT = """你是一位敏锐的心理观察者，善于从阶段性书信总结中识别一个人的长期性格与记忆倾向。

下面提供的是同一个用户若干个"5封信阶段总结"和"阶段记忆信号"。
请据此更新这个人的长期画像。

任务：
1. summary：100-200 字中文长期画像。格式："这是一个……的人。他/她……"
2. latent_place_affinities：长期反复出现的地点倾向，每项 {"name": "..."}
3. sensory_biases：长期明显的感官偏好，每项 {"name": "..."}
4. identity_signals：长期人格/身份特质，每项 {"name": "..."}
5. recent_memory_signals：最近阶段里最明显的记忆趋势，每项 {"name": "..."}

要求：
- 依据阶段总结归纳，不要编造
- recent_memory_signals 要更偏向最近阶段，而不是所有历史平均
- 输出纯 JSON，不要解释
"""

# ── 注册表 ──

PROMPT_DEFAULTS: dict[str, dict[str, str]] = {
    "letter_analysis": {
        "label": "信件分析",
        "description": "分析信件内容，提取场景、情绪、视觉主题和图像提示词。支持 {STYLE_HINT} 占位符。",
        "content": _LETTER_ANALYSIS_DEFAULT,
    },
    "poem": {
        "label": "诗歌生成",
        "description": "为明信片生成温暖怀旧的短诗。",
        "content": _POEM_DEFAULT,
    },
    "title": {
        "label": "标题生成",
        "description": "为明信片生成简短标题。",
        "content": _TITLE_DEFAULT,
    },
    "body": {
        "label": "正文生成",
        "description": '以"过去的我"口吻写明信片正文。',
        "content": _BODY_DEFAULT,
    },
    "image_prompt": {
        "label": "图像提示词",
        "description": "图像提示词生成的系统指令。",
        "content": _IMAGE_PROMPT_DEFAULT,
    },
    "batch_memory": {
        "label": "批次记忆",
        "description": "每 5 封信的批量记忆摘要生成。",
        "content": _BATCH_MEMORY_DEFAULT,
    },
    "profile": {
        "label": "人格画像",
        "description": "长期人格画像更新。",
        "content": _PROFILE_DEFAULT,
    },
}

# ── 内存缓存 ──
_cache: dict[str, str] = {}
_loaded: bool = False


async def load_cache(db: AsyncSession | None = None) -> None:
    """从数据库加载所有提示词覆盖到内存缓存。启动时调用。

    可传入已有会话，也可自行创建。
    """
    global _loaded
    if db is not None:
        await _do_load(db)
    else:
        async with async_session() as session:
            await _do_load(session)
    _loaded = True


async def _do_load(db: AsyncSession) -> None:
    rows = (await db.execute(select(PromptOverride))).scalars().all()
    _cache.clear()
    for row in rows:
        _cache[row.key] = row.content
    logger.info("提示词覆盖缓存已加载：%d 项", len(_cache))


def get_prompt(key: str, *, style_hint: str | None = None) -> str:
    """同步读取提示词。优先返回 DB 覆盖，否则返回默认。

    若提供 style_hint 且提示词中包含 {STYLE_HINT} 占位符，则替换。
    """
    content = _cache.get(key) if _loaded else None
    if content is None:
        content = PROMPT_DEFAULTS.get(key, {}).get("content", "")
    if style_hint and "{STYLE_HINT}" in content:
        content = content.replace("{STYLE_HINT}", style_hint)
    return content


async def list_prompts() -> list[dict[str, object]]:
    """返回所有提示词的元数据和当前值（覆盖或默认）。"""
    result = []
    for key, meta in PROMPT_DEFAULTS.items():
        overridden = key in _cache
        result.append({
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "content": _cache.get(key, meta["content"]),
            "defaultContent": meta["content"],
            "overridden": overridden,
        })
    return result


async def set_override(key: str, content: str, developer: str) -> None:
    """保存提示词覆盖到 DB 并更新缓存。"""
    if key not in PROMPT_DEFAULTS:
        raise KeyError(f"未知提示词: {key}")
    async with async_session() as db:
        existing = await db.scalar(select(PromptOverride).where(PromptOverride.key == key))
        if existing:
            existing.content = content
            existing.updated_by = developer
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(PromptOverride(key=key, content=content, updated_by=developer))
        await db.commit()
    _cache[key] = content
    logger.info("提示词 %s 已由 %s 更新", key, developer)


async def reset_override(key: str) -> None:
    """删除提示词覆盖，恢复默认。"""
    if key not in PROMPT_DEFAULTS:
        raise KeyError(f"未知提示词: {key}")
    async with async_session() as db:
        await db.execute(delete(PromptOverride).where(PromptOverride.key == key))
        await db.commit()
    _cache.pop(key, None)
    logger.info("提示词 %s 已重置为默认", key)
