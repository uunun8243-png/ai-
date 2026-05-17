from datetime import datetime, timezone
from src.models import NewsItem
from src.notifiers.feishu import FeishuNotifier


def test_build_monetization_card_structure():
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    items = [
        NewsItem(
            title="AI写作助手",
            url="https://example.com/ai-writer",
            source="Product Hunt",
            published=datetime.now(timezone.utc),
            summary="一款 AI 写作工具",
            analysis={
                "one_liner": "用 GPT-4 辅助内容创作",
                "business_model": "SaaS 订阅 $29/月",
                "revenue_estimate": "月收入 $10K-20K",
                "target_users": "内容创作者、博主",
                "tech_stack": "GPT-4 + Next.js",
                "why_it_works": "解决了创作者持续输出内容的痛点",
                "china_adaptation": "国内可复刻类似产品，接入国产大模型",
                "action": "调研目标用户群，确定细分场景",
            },
        ),
    ]
    card = notifier._build_monetization_card(items, "上午")
    assert "header" in card
    assert card["header"]["title"]["content"] == "💰 AI 变现项目 · 上午"
    assert card["header"]["template"] == "yellow"
    div_texts = [e["text"]["content"] for e in card["elements"] if e.get("tag") == "div"]
    assert any("AI写作助手" in t for t in div_texts)
    assert any("GPT-4" in t for t in div_texts)
    assert any("SaaS" in t for t in div_texts)


def test_build_monetization_card_empty():
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    card = notifier._build_monetization_card([], "下午")
    assert card["header"]["title"]["content"] == "💰 AI 变现项目 · 下午"


def test_send_monetization_missing_config_returns_false():
    config = {"feishu": {"app_id": "", "app_secret": "", "chat_id": ""}}
    notifier = FeishuNotifier(config)
    import asyncio
    result = asyncio.run(notifier.send_monetization([], "上午"))
    assert result is False
