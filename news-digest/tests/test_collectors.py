import pytest
from src.collectors.hackernews_collector import HackerNewsCollector
from src.collectors.blogs_collector import BlogsCollector
from src.collectors.reddit_collector import RedditCollector


@pytest.mark.asyncio
async def test_hackernews_disabled():
    c = HackerNewsCollector({"sources": {"hackernews": False}})
    assert await c.fetch() == []


@pytest.mark.asyncio
async def test_blogs_disabled():
    c = BlogsCollector({"sources": {"blogs": False}})
    assert await c.fetch() == []


@pytest.mark.asyncio
async def test_reddit_disabled():
    c = RedditCollector({"sources": {"reddit_ml": False}})
    assert await c.fetch() == []
