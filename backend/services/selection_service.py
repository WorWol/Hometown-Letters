"""筛选服务 — 图片去重和排序

搜索关键词已经是信件分析生成的精准词，筛选只做去重和截断，
不再对 URL 做关键词匹配（中文域名和英文关键词对不上）。
"""
from __future__ import annotations

from typing import Any


class SelectionService:
    """图片筛选 — 去重 + 取前 5 张"""

    def filter_relevant_images(
        self,
        image_urls: list[str],
        analysis: dict | None = None,
    ) -> list[str]:
        """去重后取前 5 张。搜索词本身已经精准，不需要再过滤"""
        if not image_urls:
            return []

        if len(image_urls) <= 3:
            return image_urls

        # 去重保留顺序
        seen: set[str] = set()
        result: list[str] = []
        for url in image_urls:
            if url not in seen:
                seen.add(url)
                result.append(url)
                if len(result) >= 5:
                    break

        return result
