"""核心写信管道 — 从 main.py 提取的 13 步流程"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Landmark, Letter, Postcard, User
from services.image_storage import get_image_url, save_image

logger = logging.getLogger(__name__)


class LetterPipeline:
    def __init__(
        self,
        llm,
        search,
        image_gen,
        landmark_svc,
        selection_svc,
        poem_svc,
    ):
        self.llm = llm
        self.search = search
        self.image_gen = image_gen
        self.landmark_svc = landmark_svc
        self.selection_svc = selection_svc
        self.poem_svc = poem_svc

    async def _search_landmark_context(self, hometown: dict) -> str:
        city = hometown.get("city", "")
        county = hometown.get("county", "")
        if not city and not county:
            return ""
        queries = [
            f"{city} 地标建筑 景点",
            f"{city} 旅游景点 推荐",
        ]
        if county:
            queries.append(f"{county} 地标 日常 老街")
            queries.append(f"{county} 公园 学校 市场")

        results = []
        for q in queries[:3]:
            try:
                items = await self.search.search_text(q, num=5)
                for item in items[:3]:
                    text = item.get("content", "").strip()
                    if text and len(text) > 10:
                        results.append(f"[{q}] {text[:150]}")
            except Exception:
                pass
        return "\n".join(results[:12]) if results else ""

    async def process(
        self,
        db: AsyncSession,
        user: User,
        text: str,
        place_hint: str = "",
        mood_hint: str = "",
    ) -> dict:
        """执行完整的 13 步写信管道，返回 {ok, data/error}"""
        logger.info("=== pipeline start user=%s day=%s ===", user.id, user.current_day)
        try:
            state = await self._load_user_hometown(db, user)
            hometown = state["hometown"]
            landmarks = state["landmarks"]

            # 1. 确保地标库
            logger.info("STEP 1: ensure_landmarks")
            if not landmarks:
                from services.landmark_service import ensure_landmarks
                landmarks = await ensure_landmarks(
                    db, user.id, hometown, self.llm, self.search
                )
            if not landmarks:
                return {"ok": False, "error": "无法生成地标库，请先设置故乡信息"}

            # 2. 检查用完，补充
            logger.info("STEP 2: check exhausted")
            search_ctx = await self._search_landmark_context(hometown)
            from services.landmark_service import refresh_if_exhausted
            await refresh_if_exhausted(
                db, user.id, hometown, self.llm, self.search, search_ctx
            )

            # 3. 选择地标
            logger.info("STEP 3: select landmark")
            from services.landmark_service import get_next_landmark
            landmark = await get_next_landmark(
                db, user.id, text, place_hint, self.llm
            )
            if not landmark:
                return {"ok": False, "error": "没有可用的地标"}

            lm_name = landmark.get("name", "故乡")
            lm_desc = landmark.get("description", "")
            lm_id = landmark.get("id", 0)

            # 4. 搜索图片
            logger.info("STEP 4: search images for %s", lm_name)
            geo = f"{hometown.get('province','')} {hometown.get('city','')} {hometown.get('county','')}"
            search_query = f"{geo} {lm_name}".strip()
            raw_image_urls = await self.search.search_images(search_query, num=6)

            # 5. 筛选图片
            logger.info("STEP 5: filter images")
            filtered_urls = self.selection_svc.filter_relevant_images(raw_image_urls, landmark)

            # 6. 搜索文字
            logger.info("STEP 6: search text")
            text_info = await self.search.search_text(search_query, num=3)
            context_str = "；".join(
                [item["content"][:120] for item in text_info[:3]]
            ) if text_info else lm_desc

            # 7. 生成诗/标题/正文
            logger.info("STEP 7: poem/title/body")
            poem = self.poem_svc.generate_poem(landmark, context_str)
            title = self.poem_svc.generate_title(landmark, poem)
            body_text = self.poem_svc.generate_body(landmark, poem, text)

            # 8. 图像提示词
            logger.info("STEP 8: image prompt")
            image_prompt = self.poem_svc.generate_image_prompt(landmark, context_str)

            # 9. 生图
            logger.info("STEP 9: generate image")
            from services.image_service import ImageService as ImgSvc
            ref_images = []
            for url in filtered_urls[:2]:
                encoded = await ImgSvc.download_and_encode(url)
                if encoded:
                    ref_images.append(encoded)
            gen_result = await self.image_gen.generate(image_prompt, reference_images=ref_images)

            # 10. 生成 ID
            pc_id = f"pc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

            # 11. 保存图片到文件系统
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

            # 12. 组装明信片
            logger.info("STEP 12: assemble postcard")
            now_ts = datetime.now(timezone.utc).isoformat()
            new_day = user.current_day + 1

            postcard = Postcard(
                user_id=user.id,
                title=title,
                body=body_text,
                poem=poem,
                place=lm_name,
                landmark_id=lm_id,
                landmark_description=lm_desc,
                mood=mood_hint or "平静",
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

            # 13. 保存
            logger.info("STEP 13: save to DB")
            from services.landmark_service import mark_landmark_used
            await mark_landmark_used(db, user.id, lm_id, new_day)
            db.add(postcard)

            letter = Letter(
                user_id=user.id,
                text=text,
                place=lm_name,
                mood=mood_hint or "平静",
                timestamp=datetime.now(timezone.utc),
            )
            db.add(letter)

            user.current_day = new_day

            await db.flush()

            logger.info("=== pipeline SUCCESS ===")
            return {
                "ok": True,
                "data": {
                    "id": pc_id,
                    "title": title,
                    "body": body_text,
                    "poem": poem,
                    "place": lm_name,
                    "landmarkId": lm_id,
                    "landmarkDescription": lm_desc,
                    "mood": mood_hint or "平静",
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

    async def _load_user_hometown(self, db: AsyncSession, user: User) -> dict:
        from db.models import Hometown
        from services.landmark_service import get_user_landmarks
        from sqlalchemy import select

        result = await db.execute(
            select(Hometown).where(Hometown.user_id == user.id)
        )
        hometown_row = result.scalar_one_or_none()
        hometown = {}
        if hometown_row:
            hometown = {
                "province": hometown_row.province or "",
                "city": hometown_row.city or "",
                "county": hometown_row.county or "",
                "hometownName": hometown_row.hometown_name or "",
            }

        landmarks = await get_user_landmarks(db, user.id)
        return {"hometown": hometown, "landmarks": landmarks}
