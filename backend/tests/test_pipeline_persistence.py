"""写信管道失败事务回归测试。"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base, Hometown, Postcard, User
from services.pipeline_service import LetterPipeline


class MockLlm:
    def chat(self, system: str, user_msg: str, **kwargs) -> str:
        if "纯 JSON" in system:
            return json.dumps({
                "visual_themes": ["旧街"],
                "emotional_tone": "怀念",
                "scene_type": "city",
                "search_keywords": ["资兴 旧街"],
                "core_place": "旧街",
                "image_prompt": "16-bit pixel art of an old street",
            }, ensure_ascii=False)
        return "旧街"


class MockSearch:
    async def search_images(self, query: str, num: int = 6):
        return ["https://images.example.com/reference.jpg"]


class MockImageGen:
    async def generate(self, prompt: str, reference_images=None):
        return {"ok": False, "error": "provider unavailable"}


class MockSelection:
    def filter_relevant_images(self, urls, analysis=None):
        return urls[:1]


class MockPoem:
    def generate_poem(self, *args, **kwargs):
        return "一首诗"

    def generate_title(self, *args, **kwargs):
        return "旧街"

    def generate_body(self, *args, **kwargs):
        return "风从旧街吹过。"


class MockMemory:
    async def load_user_context(self, db, user_id):
        return {}

    async def maybe_build_batch_memory(self, *args, **kwargs):
        return None

    async def rebuild_profile_from_batches(self, *args, **kwargs):
        return None


async def test_generation_failure_does_not_persist_postcard(monkeypatch):
    async def no_download(url: str):
        return None

    async def no_encode(url: str):
        return None

    from services.image_service import ImageService
    monkeypatch.setattr(ImageService, "download_image_bytes", no_download)
    monkeypatch.setattr(ImageService, "download_and_encode", no_encode)

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as db:
        user = User(username="pipeline-user", hashed_password="x", current_day=0)
        db.add(user)
        await db.flush()
        db.add(Hometown(user_id=user.id, province="湖南", city="郴州", county="资兴"))
        await db.flush()

        pipeline = LetterPipeline(
            llm=MockLlm(), search=MockSearch(), image_gen=MockImageGen(),
            selection_svc=MockSelection(), poem_svc=MockPoem(),
            memory_svc=MockMemory(),
        )
        result = await pipeline.process(db, user, "我想起旧街。", "旧街", "怀念")

        assert result["ok"] is False
        saved = (await db.execute(select(Postcard))).scalars().all()
        assert saved == []

    await engine.dispose()
