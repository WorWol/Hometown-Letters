"""自主写信 agent - agent 主导选图 + 构造生图场景。

架构：
  信件内容 + place_hint
      ↓
  agent 自主循环（chat_with_tools，3 个工具）
    ├─ search_web: 查证不确定实体（角色/地名/梗）
    ├─ search_images: 搜图，返回 [{url,title,source}] meta
    └─ view_image: 下载看图，返回视觉描述（审美判断）
      ↓
  agent 输出 {reference_images, image_prompt, poem, title, body, ...}
      ↓
  编排层：下载 agent 选的参考图 -> generate_image(一次) -> 保存

agent 自主决策搜什么、看哪些、选哪张、怎么构造场景；审美在 system prompt 里引导。
编排层只负责下载参考图、调一次生图、保存。
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Letter, Postcard, User
from services.llm_service import LlmService
from services.llm_utils import parse_json
from services.prompt_service import get_prompt
from services.search_service import SearchService
from services.style_service import get_analysis_hint, get_style_negative, get_style_prompt
from storage import delete_images, image_url, save_images, save_reference_images

logger = logging.getLogger("hometown")

# 工具调用次数上限，防 agent 失控消耗
_MAX_WEB_SEARCH = 3
_MAX_IMAGE_SEARCH = 4
_MAX_VIEW_IMAGE = 6
_MAX_GENERATE = 2


class LetterAgent:
    """写信 agent - 自主选图 + 构造场景，编排层负责生图和保存。"""

    def __init__(
        self,
        llm: LlmService | None = None,
        search: SearchService | None = None,
        image_gen=None,
        selection_svc=None,
        memory_svc=None,
    ):
        self.llm = llm or LlmService()
        self.search = search
        self.image_gen = image_gen
        self.memory_svc = memory_svc
        # selection_svc 保留参数兼容 lifespan 注入，agent 自主选图后不再需要

    # ── 端到端编排 ──

    async def generate_postcard(
        self,
        db: AsyncSession,
        user: User,
        text: str,
        place_hint: str = "",
        mood_hint: str = "",
        reference_image_data: bytes | None = None,
        image_style: str | None = None,
    ) -> dict:
        """端到端生成明信片：agent 自主选图+构造 -> 下载参考图 -> 生图 -> 保存。"""
        logger.info("=== agent start user=%s day=%s ===", user.id, user.current_day)
        image_keys: dict[str, str] = {}
        reference_key = ""
        reference_images_meta: list[dict] = []
        try:
            hometown = await self._load_user_hometown(db, user)
            user_context = await self.memory_svc.load_user_context(db, user.id)

            # ── STAGE 1: agent 自主完成选图 + 构造场景 ──
            logger.info("STAGE 1: letter agent (autonomous)")
            analysis = await self.run_letter_agent(
                letter_text=text,
                place_hint=place_hint,
                mood_hint=mood_hint,
                hometown=hometown if any(hometown.values()) else None,
                user_context=user_context,
                image_style=image_style,
            )
            core_place = analysis["core_place"]
            generation_place = analysis.get("generation_place") or core_place
            effective_mood = mood_hint or analysis["emotional_tone"]
            image_prompt = analysis["image_prompt"]
            poem = analysis.get("poem", "")
            title = analysis.get("title", "")
            body_text = analysis.get("body", "")
            logger.info(
                "analysis: core_place=%s refs=%d prompt=%s",
                core_place, len(analysis.get("reference_images", [])), image_prompt[:60],
            )

            # ── STAGE 2: agent 已自主生图，下载生成图 + 收集参考图 ──
            from services.image_service import ImageService
            generated_image_url = analysis.get("image_url")
            if not generated_image_url:
                raise RuntimeError("agent 未生图（image_url 为空，可能生图失败未重试成功）")
            logger.info("agent generated image url: %s", str(generated_image_url)[:120])

            # 参考图：agent 在 generate_image 时已下载验证，从缓存取
            viewed_images = analysis.pop("_viewed_images", {})
            reference_items: list[dict] = []
            if reference_image_data is not None:
                reference_items.append({
                    "data": reference_image_data, "type": "upload",
                    "entity": "", "source_url": "uploaded.png",
                })
            for ref in analysis.get("reference_images", [])[:4]:
                url = ref.get("url", "")
                data = viewed_images.get(url)
                if data:
                    reference_items.append({
                        "data": data, "type": ref.get("role", "scene"),
                        "entity": ref.get("entity", ""), "source_url": url,
                    })

            # ── STAGE 3: 下载生成图 + 保存 ──
            pc_id = (
                f"pc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
                f"-{uuid4().hex[:8]}"
            )
            image_data = await ImageService.download_image_bytes(generated_image_url)
            if not image_data:
                raise RuntimeError("generated image download failed")
            image_keys = await save_images(user.id, pc_id, image_data)
            reference_metas_raw = await save_reference_images(
                user.id, pc_id,
                [{"data": it["data"], "source_url": it["source_url"]} for it in reference_items],
            )
            reference_images_meta = [
                {**raw, "type": it["type"], "entity": it.get("entity", "")}
                for raw, it in zip(reference_metas_raw, reference_items)
            ]
            reference_key = reference_images_meta[0]["key"] if reference_images_meta else ""
            local_image_url = image_url(image_keys["card"])

            # ── STAGE 5: 保存信件 + 明信片 ──
            logger.info("STAGE 5: save letter and postcard")
            now_ts = datetime.now(timezone.utc).isoformat()
            letter = Letter(
                user_id=user.id,
                text=text,
                place=core_place,
                mood=effective_mood,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(letter)
            user.current_day += 1
            await db.flush()
            logger.info("letter saved: id=%s day=%s", letter.id, user.current_day)

            postcard = Postcard(
                user_id=user.id,
                title=title,
                body=body_text,
                poem=poem,
                place=core_place,
                generation_place=generation_place,
                mood=effective_mood,
                image_thumb_key=image_keys.get("thumb", ""),
                image_card_key=image_keys.get("card", ""),
                image_original_key=image_keys.get("original", ""),
                reference_image_key=reference_key,
                reference_images=reference_images_meta,
                image_prompt=image_prompt,
                search_image_urls=[it["source_url"] for it in reference_items],
                created_at=datetime.now(timezone.utc),
                letter_text=text,
                tags=[],
            )
            db.add(postcard)
            await db.flush()

            # ── 记忆沉淀 ──
            try:
                await self.memory_svc.maybe_build_batch_memory(db, user.id, self.llm)
                await self.memory_svc.rebuild_profile_from_batches(db, user.id, self.llm)
            except Exception:
                logger.exception("memory enrichment failed after postcard creation")

            logger.info("=== agent SUCCESS ===")
            return {
                "ok": True,
                "data": {
                    "id": pc_id,
                    "title": title,
                    "body": body_text,
                    "poem": poem,
                    "place": core_place,
                    "generationPlace": generation_place,
                    "mood": effective_mood,
                    "imageUrl": local_image_url,
                    "imageThumbUrl": image_url(image_keys.get("thumb", "")),
                    "imageOriginalUrl": image_url(image_keys.get("original", "")),
                    "referenceImageUrl": image_url(reference_key),
                    "referenceImages": [
                        {"url": image_url(m["key"]), "type": m["type"], "entity": m.get("entity", ""), "sourceUrl": m.get("source_url", "")}
                        for m in reference_images_meta
                    ],
                    "imagePrompt": image_prompt,
                    "searchImageUrls": [it["source_url"] for it in reference_items],
                    "createdAt": now_ts,
                    "letterText": text,
                    "tags": [],
                },
            }

        except Exception as e:
            if image_keys:
                try:
                    cleanup_keys = dict(image_keys)
                    for i, m in enumerate(reference_images_meta):
                        cleanup_keys[f"ref_{i}"] = m["key"]
                    await delete_images(cleanup_keys)
                except Exception:
                    logger.exception("image cleanup failed after agent error")
            tb = traceback.format_exc()
            logger.error("=== agent ERROR ===\n%s", tb)
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    # ── 自主 agent：分析 + 搜图 + 看图 + 选图 + 构造 ──

    async def run_letter_agent(
        self,
        letter_text: str,
        place_hint: str = "",
        mood_hint: str = "",
        hometown: dict | None = None,
        user_context: dict | None = None,
        image_style: str | None = None,
    ) -> dict[str, Any]:
        """agent 自主完成：分析信件 + 搜图（看 meta）+ 看图（视觉理解）+ 选参考图 + 构造 image_prompt。

        返回 {reference_images, image_prompt, poem, title, body, core_place, ...}。
        """
        if not letter_text.strip() and not place_hint.strip() and not hometown:
            return self._empty_result()

        user_msg = self._build_user_msg(letter_text, place_hint, mood_hint, hometown, user_context)

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "搜索网络了解实体背景（地名、角色、游戏梗等）。不确定的专有名词先查证再分析，不要按字面编造。",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_images",
                    "description": "搜索图片，返回 [{url, title, source}]。为场景和特指元素搜真实参考图。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "搜图关键词"},
                            "num": {"type": "integer", "description": "返回数量，默认5", "default": 5},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "view_image",
                    "description": "下载并查看图片，返回视觉描述（场景、人物形象特征、画质）。用于判断图片是否适合作参考。",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string", "description": "图片URL"}},
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "description": "下载参考图并生成图像，多张参考图会一起送给模型融合。返回 {ok:true, url} 或 {ok:false, error}。prompt 必须写清每张参考图的用途与融合关系（场景图作基底、角色图还原形象放进场景）。参考图下载失败或生图失败时换图或调整 prompt 重试。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "生图提示词"},
                            "reference_image_urls": {"type": "array", "items": {"type": "string"}, "description": "参考图URL列表"},
                        },
                        "required": ["prompt", "reference_image_urls"],
                    },
                },
            },
        ]

        from services.image_service import ImageService
        search_svc = self.search or SearchService()
        web_calls = 0
        image_search_calls = 0
        view_calls = 0
        generate_calls = 0
        viewed_images: dict[str, bytes] = {}  # 下载过的图缓存（view_image/generate_image）

        async def tool_handler(name: str, args: dict) -> str:
            nonlocal web_calls, image_search_calls, view_calls, generate_calls
            if name == "search_web":
                if web_calls >= _MAX_WEB_SEARCH:
                    return f"已达搜索次数上限({_MAX_WEB_SEARCH}次)，请基于已有信息分析"
                web_calls += 1
                query = (args.get("query") or "")[:100]
                results = await search_svc.search_web(query, num=5)
                logger.info("agent search_web[%d]: %s -> %d 条", web_calls, query, len(results))
                return json.dumps(results, ensure_ascii=False)
            if name == "search_images":
                if image_search_calls >= _MAX_IMAGE_SEARCH:
                    return "已达搜图次数上限，请基于已有结果选图"
                image_search_calls += 1
                query = (args.get("query") or "")[:100]
                num = args.get("num", 5)
                results = await search_svc.search_images(query, num=num)
                logger.info("agent search_images[%d]: %s -> %d 张", image_search_calls, query, len(results))
                return json.dumps(results, ensure_ascii=False)
            if name == "view_image":
                if view_calls >= _MAX_VIEW_IMAGE:
                    return "已达看图次数上限，请基于已有信息选图"
                view_calls += 1
                url = (args.get("url") or "")[:500]
                data = await ImageService.download_image_bytes(url)
                if not data:
                    return "图片下载失败（可能防盗链或失效），换一张试试"
                viewed_images[url] = data  # 缓存，编排层直接复用，避免重复下载
                data_url = ImageService.encode_reference_image(data, url)
                desc = await self.llm.vision_describe(
                    data_url,
                    "看图后回答：1)画质是否清晰可用；2)若是场景图，描述关键场景元素（建筑材质年代/地形植被/光线色调/地标轮廓，80字内），供构造生图场景用；3)若是角色图，判断是否目标角色并说作品名（如'鸣潮菲比立绘'或'无关少女图'）。不要描述角色形象特征（发色/服装/标志物）。",
                )
                logger.info("agent view_image[%d]: %s -> %s", view_calls, url[:60], desc[:60])
                return desc
            if name == "generate_image":
                if generate_calls >= _MAX_GENERATE:
                    return json.dumps({"ok": False, "error": "已达生图次数上限，请用已有结果输出"}, ensure_ascii=False)
                generate_calls += 1
                gen_prompt = args.get("prompt", "")
                ref_urls = args.get("reference_image_urls", [])[:4]
                # 下载参考图（优先缓存，失败反馈给 agent 换图）
                ref_data = []
                failed = []
                for rurl in ref_urls:
                    rurl = (rurl or "")[:500]
                    d = viewed_images.get(rurl)
                    if not d:
                        d = await ImageService.download_image_bytes(rurl)
                    if d:
                        viewed_images[rurl] = d
                        ref_data.append((d, rurl))
                    else:
                        failed.append(rurl)
                if failed:
                    logger.info("agent generate_image[%d]: 参考图下载失败 %d 张", generate_calls, len(failed))
                    return json.dumps({"ok": False, "error": f"参考图下载失败 {[u[:50] for u in failed]}，请换一张参考图重试"}, ensure_ascii=False)
                encoded = [ImageService.encode_reference_image(d, u) for d, u in ref_data]
                result = await self.image_gen.generate(
                    gen_prompt, reference_images=encoded,
                    style=get_style_prompt(image_style),
                    negative_prompt=get_style_negative(image_style),
                )
                if result.get("ok") and result.get("url"):
                    logger.info("agent generate_image[%d]: 生图成功 %s", generate_calls, str(result["url"])[:80])
                    return json.dumps({"ok": True, "url": result["url"]}, ensure_ascii=False)
                logger.info("agent generate_image[%d]: 生图失败 %s", generate_calls, str(result.get("error", ""))[:80])
                return json.dumps({"ok": False, "error": result.get("error", "生图失败")}, ensure_ascii=False)
            return f"未知工具: {name}"

        raw = await self.llm.chat_with_tools(
            get_prompt("letter_analysis", style_hint=get_analysis_hint(image_style)),
            user_msg,
            tools=tools,
            tool_handler=tool_handler,
            temperature=0.4,
            max_tokens=2000,
            max_rounds=15,
        )
        logger.info(
            "letter agent done: web_calls=%d image_search=%d view=%d",
            web_calls, image_search_calls, view_calls,
        )

        result = parse_json(raw)
        # 附带 view_image 缓存，供编排层复用（view 成功的图不会因重新下载失败而丢失）
        result["_viewed_images"] = viewed_images
        # 补默认值
        result.setdefault("image_url", "")
        result.setdefault("reference_images", [])
        result.setdefault("image_prompt", self._build_image_prompt(result))
        result.setdefault("poem", "")
        result.setdefault("title", "")
        result.setdefault("body", "")
        hometown_label = self._hometown_label(hometown or {})
        result.setdefault("core_place", place_hint or hometown_label)
        result.setdefault("generation_place", result.get("core_place") or hometown_label)
        result["core_place"] = result.get("core_place") or place_hint or hometown_label
        result["generation_place"] = result.get("generation_place") or result["core_place"]
        result.setdefault("emotional_tone", mood_hint or "温暖/怀念")
        result.setdefault("visual_themes", [])
        return result

    # ── 辅助 ──

    def _build_user_msg(
        self, letter_text: str, place_hint: str, mood_hint: str,
        hometown: dict | None, user_context: dict | None,
    ) -> str:
        msg_parts = []
        if letter_text.strip():
            msg_parts.append(f"信件内容：\n{letter_text}")
        if place_hint.strip():
            msg_parts.append(f"地点提示：{place_hint}")
        if mood_hint.strip():
            msg_parts.append(f"情绪提示：{mood_hint}")
        if hometown:
            hometown_label = self._hometown_label(hometown)
            if hometown_label:
                msg_parts.append(
                    f"用户保存的故乡地址是：{hometown_label}。"
                    "如果信件没有明确地点，必须使用这个故乡地址作为图片搜索后备地点，"
                    "并补充一个当地代表性景点或生活场景；如果信件明确提到了其他地点，必须以信件地点为准。"
                )
        if user_context:
            ctx_text = self._format_user_context(user_context)
            if ctx_text:
                msg_parts.append(ctx_text)
        return "\n\n".join(msg_parts)

    @staticmethod
    def _hometown_label(hometown: dict) -> str:
        return "".join(
            str(hometown.get(key, "")).strip()
            for key in ("province", "city", "county")
            if str(hometown.get(key, "")).strip()
        )

    @staticmethod
    def _format_user_context(user_context: dict) -> str:
        from services.memory_service import MemoryService
        return MemoryService().format_context_for_prompt(user_context)

    def _empty_result(self) -> dict[str, Any]:
        return {
            "reference_images": [],
            "image_prompt": chr(10).join([
                "场景主体：安静的故乡街巷，有人味的生活细节。",
                "构图与景深：方形画幅，远景天际线、中景建筑、前景小身影。",
                "角色处理：角色占画面约1/4，融入场景，背对镜头望向远方。",
                "光线与色彩：温暖怀念氛围，柔和金色夕阳光线，暖色调。",
                "氛围细节：晾衣绳、旧招牌等点睛细节。",
            ]),
            "poem": "",
            "title": "",
            "body": "",
            "core_place": "",
            "generation_place": "",
            "emotional_tone": "温暖/怀念",
            "visual_themes": [],
        }

    def _build_image_prompt(self, analysis: dict) -> str:
        """当 agent 没返回 image_prompt 时的默认拼接（不含风格词，系统会追加风格）。"""
        themes = "、".join(analysis.get("visual_themes", [])) or "安静的故乡街巷"
        tone = analysis.get("emotional_tone", "") or "温暖怀念"
        place = analysis.get("generation_place") or analysis.get("core_place", "") or ""
        place_part = f"{place}的" if place else ""
        return (
            f"场景主体：{place_part}{themes}，有人味的生活细节。\n"
            f"构图与景深：方形画幅，远景天际线、中景街巷建筑、前景人物小身影，纵深层次清晰。\n"
            f"角色处理：角色占画面约1/4，融入场景，背对镜头望向远方。\n"
            f"光线与色彩：{tone}氛围，柔和金色夕阳光线，暖色调。\n"
            f"氛围细节：晾衣绳、旧招牌等点睛细节。"
        )

    async def _load_user_hometown(self, db: AsyncSession, user: User) -> dict:
        from db.models import Hometown
        from sqlalchemy import select

        result = await db.execute(
            select(Hometown).where(Hometown.user_id == user.id)
        )
        hometown_row = result.scalar_one_or_none()
        if hometown_row:
            return {
                "province": hometown_row.province or "",
                "city": hometown_row.city or "",
                "county": hometown_row.county or "",
                "hometownName": hometown_row.hometown_name or "",
            }
        return {}
