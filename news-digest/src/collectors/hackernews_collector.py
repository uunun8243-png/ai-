import httpx
import re
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class HackerNewsCollector(BaseCollector):
    source_key = "hackernews"
    source_name = "Hacker News"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        async with httpx.AsyncClient() as client:
            resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            resp.raise_for_status()
            top_ids = resp.json()[:30]

            items = []
            for item_id in top_ids:
                resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
                resp.raise_for_status()
                data = resp.json()
                if not data or not data.get("title"):
                    continue
                # 只保留 AI 相关
                title = data.get("title", "")
                keywords = ["ai", "llm", "gpt", "claude", "machine learning",
                           "neural", "deep learning", "openai", "anthropic",
                           "gemini", "transformer", "rag", "agent"]
                title_lower = title.lower()
                if not any(re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", title_lower) for k in keywords):
                    continue
                items.append(NewsItem(
                    title=title,
                    url=data.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
                    source=self.source_name,
                    published=datetime.fromtimestamp(data.get("time", 0), tz=timezone.utc),
                    summary=data.get("text", "")[:500] or title,
                    category="行业动态",
                    score=data.get("score", 0),
                ))

        return items
