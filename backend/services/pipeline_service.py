"""核心写信管道 — 信件内容驱动的简化流程

简化架构：
  信件内容 + place_hint（主驱动）
      ↓
  阶段 1：信件深度分析（1 次 LLM）
      ↓
  阶段 2：智能图片搜索（0 次 LLM，用分析结果的关键词）
      ↓
  阶段 3：图片筛选（0 次 LLM，用分析结果的视觉主题匹配）
      ↓
  阶段 4：信件驱动的图片提示词（1 次 LLM，输入分析结果）
      ↓
  阶段 5：生图 + 诗/标题/正文（4 次 LLM，输入增强）

core_place 直接作为明信片的 place，不再经过地标库。
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Letter, Postcard, User
from services.image_storage import get_image_url, save_image

logger = logging.getLogger(__name__)


class LetterPipeline:
    def __init__(
        self,
        llm,
        search,
        image_gen,
        selection_svc,
        poem_svc,
        memory_svc,
    ):
        self.llm = llm
        self.search = search
        self.image_gen = image_gen
        self.selection_svc = selection_svc
        self.poem_svc = poem_svc
        self.memory_svc = memory_svc

    async def process(
        self,
        db: AsyncSession,
        user: User,
        text: str,
        place_hint: str = "",
        mood_hint: str = "",
    ) -> dict:
        """执行完整的写信管道，返回 {ok, data/error}"""
        logger.info("=== pipeline start user=%s day=%s ===", user.id, user.current_day)
        try:
            hometown = await self._load_user_hometown(db, user)

            # ── 加载用户记忆上下文 ──
            user_context = await self.memory_svc.load_user_context(db, user.id)

            # ── 阶段 1：信件深度分析 ──
            logger.info("STAGE 1: letter analysis")
            from services.letter_analysis_service import LetterAnalysisService
            letter_analyzer = LetterAnalysisService(self.llm)
            analysis = letter_analyzer.analyze_letter_deep(
                letter_text=text,
                place_hint=place_hint,
                mood_hint=mood_hint,
                hometown=hometown if hometown.get("city") else None,
                user_context=user_context,
            )
            logger.info(
                "analysis: core_place=%s tone=%s keywords=%s themes=%s",
                analysis["core_place"],
                analysis["emotional_tone"],
                analysis["search_keywords"],
                analysis["visual_themes"],
            )

            # 直接用 core_place 或 place_hint 作为地点
            core_place = analysis.get("core_place", "") or place_hint or "故乡"

            # ── 图片搜索（记忆点增强）──
            logger.info("STEP 2: search images (enriched with memorable spots)")
            # 获取原始搜索关键词
            search_keywords = analysis.get("search_keywords", [])
            if not search_keywords:
                geo = f"{hometown.get('province','')} {hometown.get('city','')} {hometown.get('county','')}"
                search_keywords = [f"{geo} {core_place}".strip()]

            # 尝试提取记忆点，生成增强关键词
            enriched_kws: list[str] = []
            try:
                spots = await self._get_memorable_spots(core_place)
                if len(spots) > 1:
                    # 空间集 → 用 "{地点} {记忆点}" 搜索
                    enriched_kws = [f"{core_place} {s}" for s in spots]
                    logger.info("enriched spots: %s", enriched_kws)
                else:
                    # 本身就是具体点 → 不做增强
                    logger.info("core_place is a specific spot, skip enrichment")
            except Exception as e:
                logger.warning("memorable spots extraction failed: %s", e)

            # 搜索：增强词优先，原始词替补
            all_keywords = enriched_kws + search_keywords
            all_image_urls: list[str] = []
            seen_urls: set[str] = set()
            for kw in all_keywords:
                if len(all_image_urls) >= 20:
                    break
                try:
                    urls = await self.search.search_images(kw, num=6)
                    for url in urls:
                        if url not in seen_urls:
                            seen_urls.add(url)
                            all_image_urls.append(url)
                except Exception:
                    pass
            logger.info(
                "search: %d keywords → %d unique images",
                len(all_keywords), len(all_image_urls),
            )

            # 回退：增强搜索图片不够
            if len(all_image_urls) < 10 and enriched_kws:
                logger.info("enriched search yielded only %d images, retrying with original keywords",
                            len(all_image_urls))
                for kw in search_keywords:
                    try:
                        urls = await self.search.search_images(kw, num=8)
                        for url in urls:
                            if url not in seen_urls:
                                seen_urls.add(url)
                                all_image_urls.append(url)
                    except Exception:
                        pass

            # 终极回退
            if not all_image_urls:
                geo = f"{hometown.get('province','')} {hometown.get('city','')} {hometown.get('county','')}"
                all_image_urls = await self.search.search_images(
                    f"{geo} {core_place}".strip(), num=6
                )

            # ── 图片筛选 ──
            logger.info("STEP 3: filter images by letter themes")
            filtered_urls = self.selection_svc.filter_relevant_images(
                all_image_urls, analysis
            )

            # ── 搜索文字 ──
            logger.info("STEP 4: search text")
            text_info = await self.search.search_text(core_place, num=3)
            context_str = "；".join(
                [item["content"][:120] for item in text_info[:3]]
            ) if text_info else ""

            # ── 生成诗/标题/正文 ──
            logger.info("STEP 5: poem/title/body (letter-informed)")
            simple_landmark = {"name": core_place, "description": ""}
            poem = self.poem_svc.generate_poem(simple_landmark, context_str, analysis)
            title = self.poem_svc.generate_title(simple_landmark, poem, analysis, user_context)
            body_text = self.poem_svc.generate_body(simple_landmark, poem, text, analysis, user_context)

            # ── 图像提示词 ──
            logger.info("STEP 6: image prompt (from analysis)")
            image_prompt = analysis.get("image_prompt", "")
            if not image_prompt:
                image_prompt = self.poem_svc.generate_image_prompt(
                    simple_landmark, context_str
                )

            # ── 生图 ──
            logger.info("STEP 7: generate image")
            from services.image_service import ImageService as ImgSvc
            ref_images = []
            if filtered_urls:
                encoded = await ImgSvc.download_and_encode(filtered_urls[0])
                if encoded:
                    ref_images.append(encoded)
                    tone = analysis.get("emotional_tone", "warm and nostalgic")
                    image_prompt = (
                        f"Transform the reference photo into a 16-bit pixel art scene. "
                        f"Keep the same composition, buildings, and key elements. "
                        f"Aim for a {tone} atmosphere. "
                        f"Do NOT change the subject or add unrelated elements. "
                        f"Simply pixelate and stylize the existing scene."
                    )
                else:
                    image_prompt = analysis.get("image_prompt", image_prompt)
            gen_result = await self.image_gen.generate(image_prompt, reference_images=ref_images)

            # ── 生成 ID ──
            pc_id = f"pc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

            # ── 保存图片到文件系统 ──
            local_image_url = ""
            gen_image_url = gen_result.get("url", "")
            if gen_image_url:
                try:
                    image_data = await ImgSvc.download_image_bytes(gen_image_url)
                    if image_data:
                        await save_image(pc_id, image_data, "image/jpeg")
                        local_image_url = get_image_url(pc_id)
                    else:
                        local_image_url = gen_image_url
                except Exception as dl_err:
                    logger.warning("image download error: %s", dl_err)
                    local_image_url = gen_image_url
            elif filtered_urls:
                try:
                    fallback_data = await ImgSvc.download_image_bytes(filtered_urls[0])
                    if fallback_data:
                        await save_image(pc_id, fallback_data, "image/jpeg")
                        local_image_url = get_image_url(pc_id)
                except Exception:
                    local_image_url = filtered_urls[0]

            # ── 组装明信片 ──
            logger.info("STEP 8: assemble postcard")
            now_ts = datetime.now(timezone.utc).isoformat()
            new_day = user.current_day + 1

            postcard = Postcard(
                user_id=user.id,
                title=title,
                body=body_text,
                poem=poem,
                place=core_place,
                landmark_id=None,
                landmark_description="",
                mood=mood_hint or analysis.get("emotional_tone", "平静"),
                image_path=pc_id,
                image_prompt=image_prompt,
                search_image_urls=filtered_urls,
                created_at=datetime.now(timezone.utc),
                letter_text=text,
                tags=[],
                used_fallback=False,
            )

            if not gen_result.get("ok") or not local_image_url:
                if filtered_urls:
                    local_image_url = filtered_urls[0]
                postcard.used_fallback = True

            # ── 保存 ──
            logger.info("STEP 9: save to DB")
            db.add(postcard)

            effective_mood = mood_hint or analysis.get("emotional_tone", "平静")
            letter = Letter(
                user_id=user.id,
                text=text,
                place=core_place,
                mood=effective_mood,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(letter)

            user.current_day = new_day

            await db.flush()

            # ── 每 5 封信用 LLM 重建用户画像 ──
            if new_day % 5 == 0:
                logger.info("triggering profile build at day=%d", new_day)
                try:
                    await self.memory_svc.build_profile(db, user.id, self.llm)
                except Exception as pe:
                    logger.warning("profile build failed (non-fatal): %s", pe)

            logger.info("=== pipeline SUCCESS ===")
            return {
                "ok": True,
                "data": {
                    "id": pc_id,
                    "title": title,
                    "body": body_text,
                    "poem": poem,
                    "place": core_place,
                    "landmarkId": None,
                    "landmarkDescription": "",
                    "mood": effective_mood,
                    "imageUrl": local_image_url,
                    "imagePrompt": image_prompt,
                    "searchImageUrls": filtered_urls,
                    "createdAt": now_ts,
                    "letterText": text,
                    "tags": [],
                    "usedFallback": postcard.used_fallback,
                },
            }

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("=== pipeline ERROR ===\n%s", tb)
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    async def _get_memorable_spots(self, place_name: str) -> list[str]:
        """用 LLM 判断地点类型并提取记忆点

        具体地点（桥、湖、建筑）→ 返回 [place_name]（不拆）
        空间集（校园、公园、景区）→ 返回内部有画面感的子位置列表
        """
        prompt = (
            f'判断「{place_name}」是一个具体的点（一栋建筑、一座桥、一个湖），'
            f'还是一个大的空间（校园、公园、景区、街区）。\n\n'
            f'如果是一个具体的点：只输出这个地点名称本身。\n\n'
            f'如果是一个大的空间：列出内部最有画面感、最能承载情感记忆的 3-5 个具体位置。\n'
            f'优先选有视觉特征（水、树、老建筑、光影）且能让人停留遐想的地方。\n'
            f'避免纯功能区域（停车场、宿舍楼、办公楼）。\n\n'
            f'每个地点 2-10 字。只输出地点名称，每行一个，不要编号，不要解释。'
        )
        try:
            raw = self.llm.chat(
                "你熟悉各类地点和空间的特征。",
                prompt,
                temperature=0.3,
                max_tokens=100,
            )
            spots = [s.strip() for s in raw.strip().split("\n") if s.strip()]
            if not spots:
                return [place_name]
            return spots[:5]
        except Exception as e:
            logger.warning("_get_memorable_spots LLM call failed: %s", e)
            return [place_name]

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
