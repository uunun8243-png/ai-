import pytest
from datetime import datetime, timezone
from src.models import NewsItem
from src.notifiers.feishu import FeishuNotifier, _infer_importance, _card_color


@pytest.mark.asyncio
async def test_missing_config_returns_false():
    config = {"feishu": {"app_id": "", "app_secret": "", "chat_id": ""}}
    notifier = FeishuNotifier(config)
    result = await notifier.send_news([])
    assert result is False


@pytest.mark.asyncio
async def test_partial_config_returns_false():
    config = {"feishu": {"app_id": "id", "app_secret": "", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    result = await notifier.send_news([])
    assert result is False


@pytest.mark.asyncio
async def test_send_alert_missing_config_returns_false():
    config = {"feishu": {"app_id": "", "app_secret": "", "chat_id": ""}}
    notifier = FeishuNotifier(config)
    result = await notifier.send_alert("测试阶段", "测试错误")
    assert result is False


def test_format_analysis_text_uses_new_fields():
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    item = NewsItem(
        title="GPT-5发布",
        url="https://x.com",
        source="OpenAI",
        published=datetime.now(timezone.utc),
        summary="",
        analysis={
            "category": "技术创新",
            "one_liner": "OpenAI 发布了 GPT-5，支持原生多模态",
            "background": "前代 GPT-4 仅支持文本输入",
            "core_analysis": "采用 MoE 架构，推理速度提升 3 倍",
            "why_matters": "重新定义 LLM 能力边界",
            "learning_value": "了解 MoE 大规模部署的工程挑战",
            "action": "精读原文",
            "trend": "中期趋势",
            "quick_start": "无需上手",
            "insight": "多模态是下一代 AI 的必争之地",
        },
    )
    text = notifier._format_analysis_text(item, 1, 3)
    assert "GPT-5发布" in text
    assert "1/3" in text
    assert "OpenAI 发布了 GPT-5" in text
    assert "MoE 架构" in text
    assert "多模态" in text


def test_build_card_returns_valid_structure():
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    item = NewsItem(
        title="GPT-5发布",
        url="https://x.com",
        source="OpenAI",
        published=datetime.now(timezone.utc),
        summary="",
        analysis={
            "category": "技术创新",
            "one_liner": "OpenAI 发布了 GPT-5",
            "core_analysis": "采用 MoE 架构",
            "action": "精读原文",
            "trend": "中期趋势",
            "insight": "多模态是必争之地",
        },
    )
    card = notifier._build_card(item, 1, 3)
    assert "header" in card
    assert card["header"]["title"]["content"] == "[高] GPT-5发布"
    assert card["header"]["template"] == "red"
    assert len(card["elements"]) > 0
    assert card["elements"][-1]["tag"] == "action"


def test_infer_importance():
    assert _infer_importance({"action": "动手实践"}) == "高"
    assert _infer_importance({"action": "精读原文"}) == "高"
    assert _infer_importance({"action": "关注后续"}) == "中"
    assert _infer_importance({"action": "收藏"}) == "中"
    assert _infer_importance({"action": "了解即可"}) == "低"
    assert _infer_importance({}) == "低"


def test_card_color():
    assert _card_color("高") == "red"
    assert _card_color("中") == "orange"
    assert _card_color("低") == "blue"
    assert _card_color("未知") == "blue"
