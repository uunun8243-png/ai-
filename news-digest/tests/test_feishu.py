# news-digest/tests/test_feishu.py
import pytest
from datetime import datetime, timezone
from src.models import NewsItem
from src.notifiers.feishu import FeishuNotifier


@pytest.mark.asyncio
async def test_no_webhook_returns_false():
    config = {"feishu": {"webhook_url": ""}}
    notifier = FeishuNotifier(config)
    result = await notifier.send_news([])
    assert result is False


def test_format_text_message():
    config = {"feishu": {"webhook_url": "https://example.com"}}
    notifier = FeishuNotifier(config)
    payload = notifier._format_text_message("Hello")
    assert payload["msg_type"] == "text"
    assert payload["content"]["text"] == "Hello"


def test_format_analysis_text_includes_title():
    config = {"feishu": {"webhook_url": "https://example.com"}}
    notifier = FeishuNotifier(config)
    item = NewsItem(
        title="GPT-5发布",
        url="https://x.com",
        source="OpenAI",
        published=datetime.now(timezone.utc),
        summary="",
        analysis={"importance": "高", "plain_explanation": "OpenAI发了新模型", "conclusion": "值得关注"},
    )
    text = notifier._format_analysis_text(item, 1, 3)
    assert "GPT-5发布" in text
    assert "1/3" in text
    assert "OpenAI发了新模型" in text
