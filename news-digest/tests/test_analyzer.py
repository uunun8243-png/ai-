# news-digest/tests/test_analyzer.py
import pytest
from datetime import datetime, timezone
from src.models import NewsItem
from src.analyzer import Analyzer, ANALYSIS_PROMPT


@pytest.mark.asyncio
async def test_analyzer_no_api_key_returns_error():
    config = {"deepseek": {"api_key": ""}}
    analyzer = Analyzer(config)
    item = NewsItem(
        title="Test", url="https://x.com", source="Test",
        published=datetime.now(timezone.utc), summary="Test",
    )
    result = await analyzer.analyze(item)
    assert result == {"error": "DeepSeek API key not configured"}


def test_analysis_prompt_contains_placeholders():
    prompt = ANALYSIS_PROMPT.format(
        title="GPT-5发布", source="OpenAI",
        summary="OpenAI发布了GPT-5", content="详细内容",
    )
    assert "GPT-5发布" in prompt
    assert "OpenAI" in prompt
    assert "OpenAI发布了GPT-5" in prompt
