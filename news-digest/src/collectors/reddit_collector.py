import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class RedditCollector(BaseCollector):
    source_key = "reddit_ml"
    source_name = "Reddit r/MachineLearning"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        feed = feedparser.parse("https://www.reddit.com/r/MachineLearning/.rss")
        items = []
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
