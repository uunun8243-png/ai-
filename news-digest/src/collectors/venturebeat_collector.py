import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class VentureBeatCollector(BaseCollector):
    source_key = "venturebeat"
    source_name = "VentureBeat AI"

    FEED_URL = "https://venturebeat.com/category/ai/feed/"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        items = []
        feed = feedparser.parse(self.FEED_URL)
        for entry in feed.entries[:10]:
            items.append(NewsItem(
                title=entry.title,
                url=entry.link,
                source=self.source_name,
                published=datetime(*entry.published_parsed[:6], tzinfo=timezone.utc) if entry.get("published_parsed") else datetime.now(timezone.utc),
                summary=entry.get("summary", "")[:500],
                category="行业动态",
            ))

        return items
