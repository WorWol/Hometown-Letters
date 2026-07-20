from fastapi import APIRouter

from .routers import community, letters, mail, memories, postcards, profile, state

router = APIRouter(prefix="/api", tags=["api"])
for child in (state.router, profile.router, letters.router, memories.router, postcards.router, mail.router, community.router):
    router.include_router(child)
