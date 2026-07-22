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

  core_place 作为信件地点，generation_place 记录实际用于搜图的地点。
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Letter, Postcard, User
from services.style_service import get_analysis_hint, get_style_prompt
from storage import delete_images, image_url, save_images, save_reference_image

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
        reference_image_data: bytes | None = None,
        image_style: str | None = None,
    ) -> dict:
        """执行完整的写信管道，返回 {ok, data/error}"""
        logger.info("=== pipeline start user=%s day=%s ===", user.id, user.current_day)
        image_keys: dict[str, str] = {}
        reference_key = ""
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
                hometown=hometown if any(hometown.values()) else None,
                user_context=user_context,
                style_hint=get_analysis_hint(image_style),
            )
            logger.info(
                "analysis: core_place=%s tone=%s keywords=%s themes=%s",
                analysis["core_place"],
                analysis["emotional_tone"],
                analysis["search_keywords"],
                analysis["visual_themes"],
            )

            # 地点由分析服务按“明确地点优先，否则使用家乡”规则决定。
            core_place = analysis["core_place"]
            generation_place = analysis.get("generation_place") or core_place

            # 所有外部步骤成功后，再和明信片一起保存信件。
            effective_mood = mood_hint or analysis["emotional_tone"]

            # ── 图片参考：用户上传图优先，否则使用搜索结果 ──
            if reference_image_data is not None:
                logger.info("STEP 2: use uploaded reference image")
                filtered_urls = []
                reference_data = reference_image_data
            else:
                logger.info("STEP 2: search images")
                search_keywords = analysis.get("search_keywords") or [f"{generation_place} 风景 生活场景"]
                all_image_urls = await self.search.search_images(search_keywords[0], num=5)
                if not all_image_urls:
                    raise ValueError("image search returned no results")
                logger.info("STEP 3: filter images by letter themes")
                filtered_urls = self.selection_svc.filter_relevant_images(all_image_urls, analysis)

            # ── 生成诗/标题/正文 ──
            logger.info("STEP 4: poem/title/body (letter-informed)")
            place_context = {"name": core_place, "description": ""}
            poem = self.poem_svc.generate_poem(place_context, "", analysis)
            title = self.poem_svc.generate_title(place_context, poem, analysis, user_context)
            body_text = self.poem_svc.generate_body(place_context, poem, text, analysis, user_context)

            # ── 图像提示词 ──
            logger.info("STEP 5: image prompt (from analysis)")
            image_prompt = analysis["image_prompt"]

            # ── 生图 ──
            logger.info("STEP 6: generate image")
            from services.image_service import ImageService
            if reference_image_data is None:
                if not filtered_urls:
                    raise ValueError("image selection returned no results")
                reference_data = await ImageService.download_image_bytes(filtered_urls[0])
                if not reference_data:
                    raise RuntimeError("reference image download failed")
                reference_image = ImageService.encode_reference_image(reference_data, filtered_urls[0])
            else:
                reference_image = ImageService.encode_reference_image(reference_data, "uploaded.png")
            gen_result = await self.image_gen.generate(
                image_prompt, reference_images=[reference_image],
                style=get_style_prompt(image_style),
            )
            if not gen_result.get("ok") or not gen_result.get("url"):
                raise RuntimeError(gen_result.get("error") or "image generation returned no image")

            # ── 生成 ID ──
            pc_id = (
                f"pc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
                f"-{uuid4().hex[:8]}"
            )

            # ── 保存图片到文件系统 ──
            image_data = await ImageService.download_image_bytes(gen_result["url"])
            if not image_data:
                raise RuntimeError("generated image download failed")
            image_keys = await save_images(user.id, pc_id, image_data)
            reference_key = await save_reference_image(user.id, pc_id, reference_data)
            local_image_url = image_url(image_keys["card"])

            # ── 保存信件和明信片 ──
            logger.info("STEP 7: save letter and postcard")
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
                image_prompt=image_prompt,
                search_image_urls=filtered_urls,
                created_at=datetime.now(timezone.utc),
                letter_text=text,
                tags=[],
            )

            # ── 保存明信片 ──
            logger.info("save postcard")
            db.add(postcard)
            await db.flush()

            # ── 每个用户每满 5 封信，落一批 summary/memory，并更新长期画像 ──
            try:
                await self.memory_svc.maybe_build_batch_memory(db, user.id, self.llm)
                await self.memory_svc.rebuild_profile_from_batches(db, user.id, self.llm)
            except Exception:
                logger.exception("memory enrichment failed after postcard creation")

            logger.info("=== pipeline SUCCESS ===")
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
                    "imagePrompt": image_prompt,
                    "searchImageUrls": filtered_urls,
                    "createdAt": now_ts,
                    "letterText": text,
                    "tags": [],
                },
            }

        except Exception as e:
            if image_keys:
                try:
                    await delete_images({**image_keys, "reference": reference_key})
                except Exception:
                    logger.exception("image cleanup failed after pipeline error")
            tb = traceback.format_exc()
            logger.error("=== pipeline ERROR ===\n%s", tb)
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

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
