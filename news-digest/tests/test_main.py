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
    assert len(collectors) == 6
    names = [c.source_name for c in collectors]
    assert "Arxiv" in names
    assert "GitHub Trending" in names
    assert "Hacker News" in names
