# news-digest/tests/test_main.py
from src.main import get_collectors


def test_get_collectors_returns_all_types():
    config = {
        "sources": {
            "arxiv": True, "github_trending": True, "hackernews": True,
            "blogs": True, "reddit_ml": True, "zh_sources": True,
        }
    }
    collectors = get_collectors(config)
    assert len(collectors) == 11
    names = [c.source_name for c in collectors]
    assert "Arxiv" in names
    assert "GitHub Trending" in names
    assert "Hacker News" in names
    assert "Meta AI" in names
    assert "Hugging Face" in names
    assert "Google DeepMind" in names
    assert "VentureBeat AI" in names
    assert "TechCrunch AI" in names


def test_get_monetization_collectors_returns_product_hunt():
    config = {
        "monetization": {"enabled": True},
        "sources": {"product_hunt": True},
    }
    from src.main import get_monetization_collectors
    collectors = get_monetization_collectors(config)
    assert len(collectors) == 1
    assert collectors[0].source_name == "Product Hunt"


def test_get_monetization_collectors_disabled():
    config = {"monetization": {"enabled": False}}
    from src.main import get_monetization_collectors
    assert get_monetization_collectors(config) == []
