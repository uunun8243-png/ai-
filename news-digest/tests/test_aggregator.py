# news-digest/tests/test_aggregator.py
from datetime import datetime, timezone, timedelta
from src.models import NewsItem
from src.aggregator import Aggregator


def make_item(title: str, score: float = 0, hours_ago: int = 0) -> NewsItem:
    return NewsItem(
        title=title,
        url=f"https://example.com/{title}",
        source="Test",
        published=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        summary=f"Summary of {title}",
        score=score,
    )


def test_deduplicate_exact_duplicates():
    agg = Aggregator({"analysis": {}})
    items = [make_item("Same Title"), make_item("Same Title")]
    result = agg.deduplicate(items)
    assert len(result) == 1


def test_deduplicate_similar_titles():
    agg = Aggregator({"analysis": {}})
    items = [
        make_item("GPT-5 发布：OpenAI 下一代模型"),
        make_item("GPT-5 正式发布：OpenAI 最新模型来了"),
    ]
    result = agg.deduplicate(items)
    assert len(result) == 1


def test_deduplicate_different_titles():
    agg = Aggregator({"analysis": {}})
    items = [
        make_item("GPT-5 发布"),
        make_item("Claude 4.7 发布"),
    ]
    result = agg.deduplicate(items)
    assert len(result) == 2


def test_sort_by_score():
    agg = Aggregator({"analysis": {}})
    items = [make_item("A", score=10), make_item("B", score=100), make_item("C", score=50)]
    result = agg.sort_by_score(items)
    assert [i.title for i in result] == ["B", "C", "A"]


def test_filter_recent():
    agg = Aggregator({"analysis": {}})
    items = [make_item("Old", hours_ago=72), make_item("New", hours_ago=1)]
    result = agg.filter_recent(items, hours=48)
    assert len(result) == 1
    assert result[0].title == "New"


def test_process_respects_max_per_day():
    agg = Aggregator({"analysis": {"max_news_per_day": 3}})
    items = [make_item(f"Item {i}", score=i) for i in range(10)]
    result = agg.process(items)
    assert len(result) == 3


def test_split_batches():
    agg = Aggregator({"analysis": {}})
    items = [make_item(f"Item {i}") for i in range(15)]
    morning, afternoon = agg.split_batches(items)
    assert len(morning) == 10
    assert len(afternoon) == 5


def test_split_batches_no_overflow():
    agg = Aggregator({"analysis": {}})
    items = [make_item(f"Item {i}") for i in range(5)]
    morning, afternoon = agg.split_batches(items)
    assert len(morning) == 5
    assert afternoon == []
