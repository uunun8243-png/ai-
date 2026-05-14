import pytest
from src.collectors.github_collector import GitHubTrendingCollector


@pytest.mark.asyncio
async def test_github_collector_disabled():
    config = {"sources": {"github_trending": False}}
    collector = GitHubTrendingCollector(config)
    items = await collector.fetch()
    assert items == []
