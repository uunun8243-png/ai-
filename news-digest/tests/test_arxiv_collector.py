import pytest
from src.collectors.arxiv_collector import ArxivCollector


@pytest.mark.asyncio
async def test_arxiv_collector_disabled():
    config = {"sources": {"arxiv": False}}
    collector = ArxivCollector(config)
    items = await collector.fetch()
    assert items == []


def test_arxiv_categorization():
    config = {"sources": {"arxiv": True}}
    collector = ArxivCollector(config)
    assert collector._categorize("cs.AI") == "行业动态"
    assert collector._categorize("cs.CL") == "大模型"
    assert collector._categorize("cs.LG") == "大模型"
    assert collector._categorize("cs.CV") == "多模态"
    assert collector._categorize("unknown") == "行业动态"
