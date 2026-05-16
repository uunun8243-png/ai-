from datetime import datetime, timezone
from src.models import NewsItem


def test_news_item_defaults():
    item = NewsItem(
        title="Test",
        url="https://example.com",
        source="TestSource",
        published=datetime.now(timezone.utc),
        summary="Test summary",
    )
    assert item.category == ""
    assert item.score == 0.0
    assert item.analysis is None
    assert item.content == ""


def test_news_item_with_analysis():
    item = NewsItem(
        title="Test",
        url="https://example.com",
        source="TestSource",
        published=datetime.now(timezone.utc),
        summary="Test summary",
        analysis={"trend": "LLM", "importance": "high"},
    )
    assert item.analysis["trend"] == "LLM"
