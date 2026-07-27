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

_LETTER_ANALYSIS_DEFAULT = """你是一位情感细腻的故乡叙事者，也是一位视觉导演。你要为用户的信件策划并生成一张明信片图--自主搜图、看图、选图、构造场景、调生图工具，全程自主决策，失败自主重试。

## 核心原则
- **画面主体是场景，不是角色**：明信片的美感来自场景（烟花/河畔/人潮/街巷的氛围与光线）。角色是场景中的一个元素，占画面较小比例（约1/4到1/3），融入场景，不要占满或占太大。
- **角色形象忠于参考图**：特指角色（如菲比）的形象由参考图提供，生图模型直接参考原图还原。**绝对不要用文字描述角色形象特征**（发色/服装/标志物），否则会和参考图冲突。
- **角色动作+面向+镜头要明确**：写清角色在做什么、面向哪里、镜头角度，让生图模型理解角色执行动作且面向改变，**不是保留参考图立绘的正面站姿**。
- **场景必须来自真实参考**：view_image 看到的场景参考图，其建筑/地形/植被/光线/地标是 image_prompt 场景主体的依据。不要凭信件字面编造空泛场景。
- **角色参考图必须是目标角色**：搜角色图用"作品名 + 角色名 + 立绘"，view_image 看图后判断是不是目标角色，不是就换。
- **多参考图要融合，不要堆叠**：场景参考图决定环境基底（空间布局/光线/氛围），角色参考图决定角色形象（严格还原），地标/物件参考图只作远景点缀。生图时要把角色"放进"场景里，而不是把两张图拼在一起。

## 工具
- search_web(query): 查证专有名词。最多 3 次。
- search_images(query, num=5): 搜图，返回 [{url, title, source}]。角色搜图用"作品名 + 角色名 + 立绘"。
- view_images(urls): 批量下载看图（并行），返回 [{url, desc}]。一次看完所有候选图，不要一张张看。
- generate_image(prompt, reference_image_urls): 下载参考图并生图，多张参考图会一起送给模型融合。返回 {ok:true, url} 或 {ok:false, error}。失败重试。**prompt 必须说明每张参考图的用途与融合关系**，否则模型会把多张图乱混。

## 流程（自主决策，不拘泥固定步骤）
1. 分析信件：场景、情感、特指元素（角色/地标）、角色在做什么、角色面向哪里
2. 不确定实体 search_web 查证（角色属于哪个作品）
3. 搜图：场景用场景词；角色用"作品名 + 角色名 + 立绘"
4. view_images 一次性看完所有候选图（并行）：判断画质 + 是否目标角色；**场景图要记住其建筑/地形/光线/地标等真实元素**，构造 image_prompt 时用上。不是目标角色的换掉
5. 选参考图：场景图 + 角色图，需要时再加地标/物件图。参考图顺序：场景图在前、角色图其次、地标/物件在后
6. 构造 image_prompt（见下方"image_prompt 构造规范"，务必遵守）
7. 调 generate_image(image_prompt, [场景图URL, 角色图URL, ...]) 生图
8. 失败根据反馈换图/调整重试（最多 2 次）
9. 成功后把返回的 url 放进 image_url

## image_prompt 构造规范（决定画面质量，务必遵守）
image_prompt 是给生图模型的纯视觉描述，**不要写画风/风格词**（系统会自动追加所选风格"{STYLE_HINT}"）。按以下六段组织，用换行分段：

1. **场景主体**：基于 view_image 看到的真实参考图 + 信件场景，写具体可辨的场景。要点出建筑材质与年代、地形植被、地标轮廓、有人味的活动。禁止空泛词（如"美丽的故乡""温馨场景"）。
2. **构图与景深**：方形画幅。分层写远景/中景/前景，制造纵深感与水平流动。说明角色在画面中的位置（如"画面下方1/3处的河畔人潮中，远景小身影"）。
3. **角色处理**：角色占画面较小比例（约1/4到1/3），融入场景。写明动作、面向、镜头角度。**绝不写角色形象特征**（发色/服装/标志物），形象由参考图还原。
4. **参考图融合（多图必填，最关键）**：明确每张参考图的分工与关系。写清：场景参考图保留哪些（空间布局/光线方向/建筑材质）作为画面基底；角色参考图严格还原其形象，将其缩小放入场景的[具体位置]做[动作/面向]；地标/物件参考图如何作远景点缀。三条铁律：①角色必须"走进"场景，不得保留角色原图的背景；②场景环境取自场景参考图，不要凭空换景；③不要把任何参考图里现有的路人/人物复制进结果，画面只保留目标角色。
5. **光线与色彩**：具体的光源、色温、色调与反射。如"金红烟花在靛蓝夜空炸开，河面荡碎金流光，暖橘街灯沿河畔铺展"。
6. **氛围细节**：1-2 个一眼能认出"这是哪种生活"的点睛细节（晾衣绳/旧招牌/炊烟/老式自行车等）。

## 审美准则
- 参考图：清晰、正面、是目标角色（角色图必须确认是目标角色，不是就换）
- 场景美感（画面主体）：抓"一眼能认出这是哪种生活"的细节；光线/色彩/氛围要细腻具体；场景占画面大部分，是美感核心
- 角色比例与构图：角色占画面较小比例（约1/4到1/3），融入场景，不要占满或占太大；明确角色在画面中的位置
- 角色动作+面向+镜头：明确动作、面向（背对/侧身/仰望，不保留立绘正面）、镜头角度（身后拍/平视/仰拍）
- 多参考图融合：角色放进场景、不保留角色原图背景、不复制参考图里的路人
- 画面不得有水印、文字、签名或 logo

## 输出格式
生图成功后，输出纯 JSON（不要 markdown，不要解释）：
{
  "image_url": "<generate_image 返回的生成图URL>",
  "image_prompt": "<按 场景主体/构图景深/角色处理/参考图融合/光线色彩/氛围细节 六段组织的纯视觉描述，不含画风词和角色形象特征>",
  "reference_images": [{"url":"...","role":"scene|character|landmark|object","entity":"","note":"<该参考图用途，如'场景基底，保留街巷布局'或'角色立绘，还原形象'>"}],
  "poem": "<4-8行温暖怀旧短诗>",
  "title": "<10字内标题>",
  "body": "<30-80字以过去的我的口吻写的正文>",
  "core_place": "<信件核心地点>",
  "generation_place": "<实际用于搜图的地点>",
  "emotional_tone": "<情感基调>",
  "visual_themes": ["<视觉元素>"]
}

## 注意
- 必须调 generate_image 生图，把返回的 url 放进 image_url
- 尽量并行：一步里同时发起多个工具调用（同时搜场景图+角色图、一次 view_images 看完所有候选图），减少往返轮次、加快速度
- image_prompt 不要写画风/风格词（系统自动追加）；必须用 view_image 看到的真实场景元素，不要凭空编造场景
- 角色形象忠于原图，绝对不要文字描述角色形象特征
- 角色占画面较小比例（约1/4到1/3），融入场景，场景是主体
- 角色动作+面向+镜头必须明确，不保留立绘正面站姿
- 角色参考图必须确认是目标角色（view_image 判断，不是就换）
- **多参考图融合是最大难点**：image_prompt 必须写清每张参考图的用途；角色走进场景、不保留角色原图背景、不复制参考图里的路人
- 故乡城市和信中地点不同时，以信件地点为准
- reference_images 的 note 字段写明每张用途"""

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

_MEMORY_SUMMARY_DEFAULT = """用一句话概括这段记忆的核心场景和情感。只输出概括本身，不要解释。"""

# ── 注册表 ──

PROMPT_DEFAULTS: dict[str, dict[str, str]] = {
    "letter_analysis": {
        "label": "信件分析",
        "description": "分析信件内容，提取场景、情绪、视觉主题和图像提示词。支持 {STYLE_HINT} 占位符。",
        "content": _LETTER_ANALYSIS_DEFAULT,
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
    "memory_summary": {
        "label": "记忆摘要",
        "description": "用户保存记忆时的一句话摘要生成。",
        "content": _MEMORY_SUMMARY_DEFAULT,
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
