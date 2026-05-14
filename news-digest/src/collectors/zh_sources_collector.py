import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class ZhSourcesCollector(BaseCollector):
    source_key = "zh_sources"
    source_name = "中文科技媒体"

    FEEDS = {
        "机器之心": "https://www.jiqizhixin.com/rss",
        "量子位": "https://www.qbitai.com/feed",
    }

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        items = []
        for source_name, feed_url in self.FEEDS.items():
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                items.append(NewsItem(
                    title=entry.title,
                    url=entry.link,
                    source=source_name,
                    published=datetime(*entry.published_parsed[:6], tzinfo=timezone.utc) if entry.get("published_parsed") else datetime.now(timezone.utc),
                    summary=entry.get("summary", "")[:500],
                    category="行业动态",
                ))

        return items
