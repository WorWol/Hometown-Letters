from fastapi import APIRouter

from .routers import admin, admin_data, community, letters, mail, memories, postcards, profile, state

router = APIRouter(prefix="/api", tags=["api"])
for child in (state.router, profile.router, letters.router, memories.router, postcards.router, mail.router, community.router, admin.router, admin_data.router):
    router.include_router(child)
