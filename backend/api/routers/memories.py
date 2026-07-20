from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import Memory, User
from .common import get_llm

router = APIRouter(tags=["memories"])


class MemorySaveReq(BaseModel):
    text: str
    tags: list[str] = Field(default_factory=list)
    place_hint: str = ""


@router.post("/memory/save")
async def save_memory(body: MemorySaveReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), llm=Depends(get_llm)):
    memory = Memory(user_id=user.id, text=body.text, tags=body.tags, place_hint=body.place_hint, timestamp=datetime.now(timezone.utc), analysis_status="pending")
    db.add(memory)
    await db.flush()
    memory.summary = llm.chat("用一句话概括这段记忆的核心场景和情感。", body.text, temperature=0.5, max_tokens=100)
    memory.analysis_status = "completed"
    await db.flush()
    return {"ok": True, "data": {"id": f"mem-{memory.id}", "text": memory.text, "tags": memory.tags, "placeHint": memory.place_hint, "timestamp": memory.timestamp.isoformat(), "analysisStatus": memory.analysis_status, "summary": memory.summary}}
