# news-digest/tests/test_main.py
from src.main import get_collectors


def test_get_collectors_returns_all_types():
    config = {
        "sources": {
            "arxiv": True, "github_trending": True, "hackernews": True,
            "openai_blog": True, "anthropic_blog": True, "google_ai_blog": True,
            "reddit_ml": True, "jiqizhixin": True, "liangziwei": True,
        }
    }
    collectors = get_collectors(config)
    assert len(collectors) == 6
