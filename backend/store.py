"""内存存储 — 管理游戏状态 + 地标库 + 图片缓存"""
from typing import Any
from datetime import datetime


class GameStore:
    def __init__(self):
        self._users: dict[str, dict[str, Any]] = {}
        self._image_cache: dict[str, tuple[bytes, str]] = {}  # postcard_id → (bytes, content_type)

    def _ensure(self, user_id: str) -> dict:
        if user_id not in self._users:
            self._users[user_id] = {
                "current_day": 0,
                "hometown": {},
                "profile": {},
                "letters": [],
                "memories": [],
                "postcards": [],
                "past_self_profile": {},
                "landmarks": [],       # 地标库
                "used_landmark_ids": [],  # 已用过的地标 ID 列表
                "settings": {},
            }
        return self._users[user_id]

    # ─── 基础状态 ───

    def get_game_state(self, user_id: str) -> dict[str, Any]:
        s = self._ensure(user_id)
        return {
            "current_day": s["current_day"],
            "hometown": s["hometown"],
            "profile": s["profile"],
            "letters": s["letters"][-20:],
            "memories": s["memories"][-40:],
            "postcards": s["postcards"][-100:],
            "past_self_profile": s["past_self_profile"],
            "landmarks": s["landmarks"],
        }

    def init_hometown(self, user_id: str, hometown: dict, profile: dict) -> None:
        s = self._ensure(user_id)
        s["hometown"] = hometown
        s["profile"] = profile

    # ─── 地标库 ───

    def get_landmarks(self, user_id: str) -> list[dict]:
        return self._ensure(user_id)["landmarks"]

    def set_landmarks(self, user_id: str, landmarks: list[dict]) -> None:
        self._ensure(user_id)["landmarks"] = landmarks

    def get_used_landmark_ids(self, user_id: str) -> list[str]:
        return self._ensure(user_id)["used_landmark_ids"]

    def mark_landmark_used(self, user_id: str, landmark_id: str) -> None:
        s = self._ensure(user_id)
        if landmark_id not in s["used_landmark_ids"]:
            s["used_landmark_ids"].append(landmark_id)
        # 更新地标自身计数
        for lm in s["landmarks"]:
            if lm.get("id") == landmark_id:
                lm["used_count"] = lm.get("used_count", 0) + 1
                lm["last_used_day"] = s["current_day"]
                break

    def get_unused_landmarks(self, user_id: str) -> list[dict]:
        s = self._ensure(user_id)
        used = set(s["used_landmark_ids"])
        return [lm for lm in s["landmarks"] if lm.get("id") not in used]

    def are_all_landmarks_used(self, user_id: str) -> bool:
        s = self._ensure(user_id)
        return len(s["used_landmark_ids"]) >= len(s["landmarks"]) > 0

    # ─── 信件/记忆/明信片 ───

    def add_letter(self, user_id: str, letter: dict) -> dict:
        s = self._ensure(user_id)
        s["letters"].append(letter)
        return letter

    def add_memory(self, user_id: str, memory: dict) -> dict:
        s = self._ensure(user_id)
        s["memories"].insert(0, memory)
        if len(s["memories"]) > 40:
            s["memories"] = s["memories"][:40]
        return memory

    def add_postcard(self, user_id: str, postcard: dict) -> dict:
        s = self._ensure(user_id)
        s["postcards"].append(postcard)
        s["current_day"] += 1
        return postcard

    def update_past_self_profile(self, user_id: str, profile: dict) -> None:
        self._ensure(user_id)["past_self_profile"] = profile

    def set_settings(self, user_id: str, settings: dict) -> None:
        self._ensure(user_id)["settings"] = settings

    # ─── 图片缓存 ───

    def cache_image(self, postcard_id: str, image_data: bytes,
                    content_type: str = "image/jpeg") -> None:
        """缓存生成的图片，key 为明信片 ID"""
        self._image_cache[postcard_id] = (image_data, content_type)

    def get_cached_image(self, postcard_id: str) -> tuple[bytes, str] | None:
        """获取缓存的图片，返回 (image_bytes, content_type) 或 None"""
        return self._image_cache.get(postcard_id)


store = GameStore()
