import pytest
from src.collectors.zh_sources_collector import ZhSourcesCollector


@pytest.mark.asyncio
async def test_zh_sources_disabled():
    c = ZhSourcesCollector({"sources": {"zh_sources": False}})
    assert await c.fetch() == []
