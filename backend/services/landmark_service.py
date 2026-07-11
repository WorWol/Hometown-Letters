"""地标库服务 — 管理用户故乡的地标建筑库

地标分两个层级：
  - tier="city"   市级地标：全市范围的大标志性建筑/旅游景点
  - tier="county" 区县级地标：具体区县的小记忆点/生活场景

生成方式：通过网络搜索真实地标信息 + LLM 基于搜索结果整理，
而非仅靠模型内部训练数据。
"""
from __future__ import annotations

import json
import logging
from typing import Any
from datetime import datetime

from services.llm_service import LlmService

logger = logging.getLogger("hometown")


SYSTEM_SEED_LANDMARKS = """你是一位熟悉中国地标的乡土专家。

下面是从网络搜索到的该地区真实地标信息（搜索结果）。
请根据这些搜索结果，结合你的知识，整理出两个层级的地标：

## 第一层：市级地标（全市范围的大标志性建筑/旅游景点）
- 整个地级市范围内最有名的 5 个地标
- 旅游景点、历史建筑、城市名片级别

## 第二层：区县级地标（具体区县的小记忆点/生活场景）
- 该区县特有的 5 个小场景
- 本地人日常会去的地方：公园、学校、菜市场、老街、散步道

场景类型 (scene_type)：lakeside_dam, bridge_roadside, school_gate, street_food, path_to_pond, park, market, temple, mountain, other

返回纯 JSON 数组（10个），不要 markdown，不要多余文字：
[
  {"name": "东江湖", "description": "著名湖泊景区，雾漫小东江的摄影胜地", "scene_type": "lakeside_dam", "tier": "city"},
  {"name": "秀流公园", "description": "市区老公园，承载几代人记忆，晚上很多人散步", "scene_type": "park", "tier": "county"}
]

city 在前 5 个，county 在后 5 个。""" + " 参考搜索结果中的真实地名，不要凭空编造。"


SYSTEM_SUPPLEMENT_LANDMARKS = """用户的地标库已经循环用完一轮了。
下面是网络搜索到的该地区真实地标信息。

请从搜索结果中挑选与已有地标不重复的 2-4 个新地标补充进去。
同样分两个层级：
- tier="city"（市级大标志建筑/旅游景点）
- tier="county"（区县小记忆点/生活场景）

纯 JSON 数组，不要 markdown。""" + " 优先从搜索结果的真实名称中选取。"


class LandmarkService:
    """地标库管理服务"""

    def __init__(self, llm: LlmService | None = None):
        self.llm = llm or LlmService()
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"lm-{datetime.now().strftime('%m%d')}-{self._id_counter:04d}"

    def ensure_landmarks(self, user_id: str, hometown: dict,
                         store_instance,
                         search_context: str = "") -> list[dict]:
        """确保地标库存在，支持传入联网搜索结果"""
        landmarks = store_instance.get_landmarks(user_id)
        if landmarks:
            return landmarks
        return self._seed_landmarks(user_id, hometown, store_instance, search_context)

    def refresh_if_exhausted(self, user_id: str, hometown: dict,
                             store_instance,
                             search_context: str = "") -> list[dict]:
        """用完了直接重置循环使用，同时用搜索结果补充少量新品"""
        if not store_instance.are_all_landmarks_used(user_id):
            return store_instance.get_landmarks(user_id)

        # 清空使用记录 → 旧地标重新进池子（循环复用）
        store_instance._ensure(user_id)["used_landmark_ids"] = []

        # 同时尝试补充 2-4 个新的（从搜索结果的真实信息里来）
        if search_context.strip():
            try:
                new_lm = self._supplement_from_search(
                    user_id, store_instance, search_context
                )
                if new_lm:
                    existing = store_instance.get_landmarks(user_id)
                    store_instance.set_landmarks(user_id, existing + new_lm)
            except Exception:
                pass

        return store_instance.get_landmarks(user_id)

    def get_next_landmark(self, user_id: str, store_instance,
                          letter_text: str = "",
                          place_hint: str = "") -> dict | None:
        """获取下一个地标 — 结合用户信的内容和地点提示智能匹配"""
        unused = store_instance.get_unused_landmarks(user_id)
        all_lm = store_instance.get_landmarks(user_id)
        
        used_ids = store_instance.get_used_landmark_ids(user_id)

        # 1. 用户指定地点 hint → 在所有地标中找匹配
        if place_hint.strip():
            hint_clean = place_hint.strip()
            # 从所有地标（含已使用的）中找匹配，不限于未使用
            matchup_lm = unused if unused else all_lm
            exact_matches = []
            partial_matches = []
            fuzzy_matches = []
            for lm in matchup_lm:
                name = lm.get("name", "")
                desc = lm.get("description", "")
                combined_text = f"{name} {desc}"
                if hint_clean in name:
                    exact_matches.append(lm)
                elif hint_clean in combined_text:
                    partial_matches.append(lm)
                else:
                    # 字符级模糊匹配：计算两字符串中共同字符出现的比例
                    lhs = set(hint_clean)
                    rhs = set(name)
                    if lhs and rhs:
                        overlap = len(lhs & rhs) / max(len(lhs), len(rhs))
                        if overlap >= 0.5:
                            fuzzy_matches.append((overlap, lm))
            if exact_matches:
                logger.info("place_hint exact match: %s → %s", place_hint, exact_matches[0].get("name"))
                return exact_matches[0]
            if partial_matches:
                logger.info("place_hint partial match: %s → %s", place_hint, partial_matches[0].get("name"))
                return partial_matches[0]
            if fuzzy_matches:
                fuzzy_matches.sort(key=lambda x: x[0], reverse=True)
                best = fuzzy_matches[0][1]
                logger.info("place_hint fuzzy match: %s → %s (score=%.2f)", place_hint, best.get("name"), fuzzy_matches[0][0])
                return best
            # 没匹配到 → 把 place_hint 作为新的自定义地标插入
            logger.info("place_hint '%s' not found in landmarks, creating custom landmark", place_hint)
            custom_lm = {
                "name": hint_clean,
                "description": f"用户指定的地点：{hint_clean}",
                "scene_type": "bridge_roadside",
                "tier": "county",
                "id": self._next_id(),
                "used_count": 0,
                "last_used_day": None,
                "source": "user_place_hint",
                "created_at": datetime.now().isoformat(),
            }
            all_lm = store_instance.get_landmarks(user_id)
            store_instance.set_landmarks(user_id, all_lm + [custom_lm])
            return custom_lm

        if not unused:
            # 全部用完 → 重置（安全兜底）
            store_instance._ensure(user_id)["used_landmark_ids"] = []
            return all_lm[0] if all_lm else None

        # 2. 用户写了信 → LLM 从所有未使用地标中挑选
        if letter_text.strip() and len(unused) > 1:
            chosen = self._select_best_landmark(unused, letter_text)
            if chosen:
                logger.info("LLM selected landmark from %d unused: %s", len(unused), chosen.get("name"))
                return chosen

        # 3. 兜底：按层级交替选择
        used_city = sum(1 for lm in all_lm if lm.get("tier") == "city"
                        and lm.get("id") in used_ids)
        used_county = sum(1 for lm in all_lm if lm.get("tier") == "county"
                          and lm.get("id") in used_ids)

        prefer_tier = "county" if used_county < used_city else "city"
        candidates = [lm for lm in unused if lm.get("tier") == prefer_tier]
        if not candidates:
            other = "county" if prefer_tier == "city" else "city"
            candidates = [lm for lm in unused if lm.get("tier") == other]
        if not candidates:
            candidates = unused

        return candidates[0]

    # ─── 内部方法 ───

    def _seed_landmarks(self, user_id: str, hometown: dict,
                        store_instance, search_context: str = "") -> list[dict]:
        """联网搜索 + LLM 播种地标 — 5 city + 5 county"""
        hometown_str = (
            f"地级市：{hometown.get('city', '')}\n"
            f"下辖区县：{hometown.get('county', '')}\n"
            f"省：{hometown.get('province', '')}\n"
            f"名称：{hometown.get('hometownName', '')}"
        ).strip()

        user_msg = f"地区信息：\n{hometown_str}"
        if search_context:
            user_msg += f"\n\n网络搜索结果（请参考）：\n{search_context[:1200]}"
        user_msg += "\n\n请生成该地区两个层级的地标（共10个）。"

        try:
            raw = self.llm.chat(
                SYSTEM_SEED_LANDMARKS,
                user_msg,
                temperature=0.7,
                max_tokens=1200,
            )
            landmarks = self._parse_landmarks(raw)
        except Exception:
            landmarks = []

        # LLM 异常时的 fallback
        if not landmarks:
            landmarks = [
                {"name": "东江湖", "description": "著名湖泊景区", "scene_type": "lakeside_dam", "tier": "city"},
                {"name": "裕后街", "description": "保存完好的明清古街", "scene_type": "street_food", "tier": "city"},
                {"name": "大草原", "description": "城郊辽阔的高山草原", "scene_type": "park", "tier": "city"},
                {"name": "苏仙岭", "description": "城市边的名山，可俯瞰全城", "scene_type": "mountain", "tier": "city"},
                {"name": "北湖公园", "description": "市中心老公园", "scene_type": "park", "tier": "city"},
                {"name": "秀流公园", "description": "市区老公园，承载几代人记忆", "scene_type": "park", "tier": "county"},
                {"name": "步行街", "description": "县城最繁华的商业街", "scene_type": "street_food", "tier": "county"},
                {"name": "市立中学", "description": "老牌中学门口的梧桐树和早点摊", "scene_type": "school_gate", "tier": "county"},
                {"name": "东江吊桥", "description": "横跨东江的铁索桥", "scene_type": "bridge_roadside", "tier": "county"},
                {"name": "鲤鱼江市场", "description": "本地人爱逛的菜市场", "scene_type": "market", "tier": "county"},
            ]

        now = datetime.now().isoformat()
        for lm in landmarks:
            lm.setdefault("tier", "county")
            lm["id"] = self._next_id()
            lm["used_count"] = 0
            lm["last_used_day"] = None
            lm["source"] = "web_search_seed"
            lm["created_at"] = now

        store_instance.set_landmarks(user_id, landmarks)
        store_instance._ensure(user_id)["used_landmark_ids"] = []
        return landmarks

    def _supplement_from_search(self, user_id: str,
                                store_instance,
                                search_context: str) -> list[dict]:
        """从搜索结果中补充新地标"""
        existing = store_instance.get_landmarks(user_id)
        existing_names = [lm["name"] for lm in existing if "name" in lm]

        user_msg = (
            f"已有地标：{'、'.join(existing_names)}\n\n"
            f"网络搜索结果：\n{search_context[:1200]}\n\n"
            f"请从搜索结果中挑选 2-4 个与已有地标不重复的补充。"
        )
        raw = self.llm.chat(
            SYSTEM_SUPPLEMENT_LANDMARKS,
            user_msg,
            temperature=0.7,
            max_tokens=800,
        )
        new_lm = self._parse_landmarks(raw)
        now = datetime.now().isoformat()
        for lm in new_lm:
            lm.setdefault("tier", "county")
            lm["id"] = self._next_id()
            lm["used_count"] = 0
            lm["last_used_day"] = None
            lm["source"] = "web_search_supplement"
            lm["created_at"] = now
        return new_lm

    def _select_best_landmark(self, candidates: list[dict],
                              user_context: str) -> dict | None:
        """用 LLM 从候选地标中根据用户信件内容+地点提示选最匹配的"""
        if len(candidates) == 1:
            return candidates[0]
        names = [f"{lm['name']}（{lm.get('description', '')}）[{lm.get('scene_type', '')}]"
                 for lm in candidates]
        prompt = (
            f"用户输入：{user_context}\n\n"
            f"候选地标：\n" + "\n".join(
                f"{i+1}. {n}" for i, n in enumerate(names)
            ) + "\n\n选最贴切的一个，只输出数字。"
        )
        try:
            raw = self.llm.chat(
                "你是一位故乡地理专家。根据用户描述的情感、地点和场景，从候选地标中选出最贴近的一个。只看名字+描述就够，不要过度分析。只输出数字。",
                prompt, temperature=0.3, max_tokens=10,
            )
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
        except (ValueError, IndexError, Exception):
            pass
        return candidates[0]

    @staticmethod
    def _parse_landmarks(raw: str) -> list[dict]:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            clean = clean.rsplit("\n", 1)[0]
            if clean.endswith("```"):
                clean = clean[:-3]
        data = json.loads(clean)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "landmarks" in data:
            return data["landmarks"]
        return []
