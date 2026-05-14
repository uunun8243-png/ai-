import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class BlogsCollector(BaseCollector):
    source_key = "blogs"
    source_name = "AI Blog"

    FEEDS = {
        "openai_blog": ("OpenAI", "https://openai.com/blog/feed.xml"),
        "anthropic_blog": ("Anthropic", "https://www.anthropic.com/feed.xml"),
        "google_ai_blog": ("Google AI", "https://blog.research.google/feed.xml"),
    }

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        items = []
        for key, (source_name, feed_url) in self.FEEDS.items():
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
