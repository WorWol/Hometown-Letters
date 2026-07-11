"""筛选服务 — 地标选择 + 图片相关性过滤

职责：
1. 从搜索结果中过滤出与地标真正相关的图片
2. 用 LLM 判断图片 URL 是否与地标描述匹配
"""
from __future__ import annotations

from typing import Any

from services.llm_service import LlmService


SYSTEM_FILTER_IMAGES = """你是一位严格的图片审核员。
给定一个地标和一组图片 URL（含上下文信息），判断哪些图片与该地标真正相关。

规则：
- 只选择确实包含该地标或直接相关场景的图片
- 排除：不相关的风景图、广告图、不明确的缩略图
- 返回 JSON 数组，元素为相关图片的 URL（或索引），空数组表示都不相关

返回格式：["url1", "url2"] 或 []
"""


class SelectionService:
    """地标/图片的筛选服务"""

    def __init__(self, llm: LlmService | None = None):
        self.llm = llm or LlmService()

    def filter_relevant_images(self, image_urls: list[str],
                               landmark: dict) -> list[str]:
        """从搜索结果中筛选与地标真正相关的图片"""
        if not image_urls:
            return []

        if len(image_urls) <= 3:
            # 图片很少时，全部保留
            return image_urls

        # 让 LLM 筛选
        lm_name = landmark.get("name", "")
        lm_desc = landmark.get("description", "")

        urls_text = "\n".join(
            f"{i+1}. {url}" for i, url in enumerate(image_urls)
        )
        prompt = (
            f"地标：{lm_name}\n"
            f"描述：{lm_desc}\n\n"
            f"图片 URL 列表：\n{urls_text}\n\n"
            f"请返回与此地标真正相关的图片 URL（最多3张），格式为 JSON 数组。"
        )

        try:
            raw = self.llm.chat(
                SYSTEM_FILTER_IMAGES,
                prompt,
                temperature=0.2,
                max_tokens=300,
            )
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                clean = clean.rsplit("\n", 1)[0]
                if clean.endswith("```"):
                    clean = clean[:-3]

            import json
            filtered = json.loads(clean)
            if isinstance(filtered, list):
                # 支持返回 URL 或索引
                result = []
                for item in filtered:
                    item_str = str(item).strip()
                    if item_str in image_urls:
                        result.append(item_str)
                    elif item_str.isdigit():
                        idx = int(item_str) - 1
                        if 0 <= idx < len(image_urls):
                            result.append(image_urls[idx])
                return result[:3]
        except Exception:
            pass

        # LLM 失败时返回前 3 张
        return image_urls[:3]
