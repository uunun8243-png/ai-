import asyncio
from datetime import datetime, timezone
from typing import List

import arxiv

from src.models import NewsItem
from src.collectors.base import BaseCollector


class ArxivCollector(BaseCollector):
    source_key = "arxiv"
    source_name = "Arxiv"

    CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        items = []

        for cat in self.CATEGORIES:
            try:
                cat_items = await asyncio.to_thread(self._fetch_category, cat)
                items.extend(cat_items)
            except Exception:
                print(f"  ⚠ Arxiv category '{cat}' 获取失败，跳过")

        return items

    def _fetch_category(self, category: str) -> List[NewsItem]:
        """同步辅助函数，在 asyncio.to_thread 中运行。"""
        cat_items: List[NewsItem] = []

        client = arxiv.Client()
        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=20,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        for result in client.results(search):
            published = result.published
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)

            cat_items.append(NewsItem(
                title=result.title,
                url=result.entry_id,
                source=self.source_name,
                published=published,
                summary=result.summary[:500],
                category=self._categorize(category),
            ))

        return cat_items

    def _categorize(self, category: str) -> str:
        mapping = {
            "cs.AI": "行业动态",
            "cs.CL": "大模型",
            "cs.LG": "大模型",
            "cs.CV": "多模态",
        }
        return mapping.get(category, "行业动态")
