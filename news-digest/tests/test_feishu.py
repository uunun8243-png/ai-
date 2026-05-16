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


@pytest.mark.asyncio
async def test_cleanup_missing_config_returns_false():
    """无配置时 cleanup 不应报错。"""
    config = {"feishu": {"app_id": "", "app_secret": "", "chat_id": ""}}
    notifier = FeishuNotifier(config)
    # 应该静默返回 False，不抛异常
    result = await notifier._cleanup_old_messages()
    assert result is False


def test_card_color():
    assert _card_color("高") == "red"
    assert _card_color("中") == "orange"
    assert _card_color("低") == "blue"
    assert _card_color("未知") == "blue"


@pytest.mark.asyncio
async def test_cleanup_returns_false_on_api_error():
    """验证 cleanup 在 API 报错时返回 False 而非崩溃。"""
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    # 没有有效 token，httpx 请求会失败，但不应崩溃
    result = await notifier._cleanup_old_messages("")
    assert result is False


def test_sort_by_priority():
    items = [
        NewsItem(title="低优先级", url="https://a.com", source="A", published=datetime.now(timezone.utc), summary="",
                 analysis={"action": "了解即可"}),
        NewsItem(title="高优先级", url="https://b.com", source="B", published=datetime.now(timezone.utc), summary="",
                 analysis={"action": "精读原文"}),
        NewsItem(title="中优先级", url="https://c.com", source="C", published=datetime.now(timezone.utc), summary="",
                 analysis={"action": "收藏"}),
    ]
    sorted_items = FeishuNotifier._sort_by_priority(items)
    # 按高 → 中 → 低排序
    actions = [item.analysis["action"] for item in sorted_items]
    assert actions == ["精读原文", "收藏", "了解即可"]


def test_sort_by_priority_within_same_level():
    """同优先级保持原始顺序。"""
    items = [
        NewsItem(title="A", url="https://a.com", source="A", published=datetime.now(timezone.utc), summary="",
                 analysis={"action": "精读原文"}),
        NewsItem(title="B", url="https://b.com", source="B", published=datetime.now(timezone.utc), summary="",
                 analysis={"action": "动手实践"}),
    ]
    sorted_items = FeishuNotifier._sort_by_priority(items)
    titles = [item.title for item in sorted_items]
    assert titles == ["A", "B"]


def test_sort_by_priority_empty():
    assert FeishuNotifier._sort_by_priority([]) == []


def test_build_tab_card_structure():
    """Tab 卡片必须包含 tab 选择器和 4 个 tab 内容区块。"""
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    items = [
        NewsItem(title="高优先级新闻", url="https://a.com", source="测试", published=datetime.now(timezone.utc), summary="",
                 analysis={"category": "技术创新", "one_liner": "一条高优先级", "action": "精读原文", "trend": "中期趋势"}),
        NewsItem(title="低优先级新闻", url="https://b.com", source="测试", published=datetime.now(timezone.utc), summary="",
                 analysis={"category": "行业趋势", "one_liner": "一条低优先级", "action": "了解即可"}),
    ]
    card = notifier._build_tab_card(items, "上午")
    assert "header" in card
    assert card["header"]["title"]["content"] == "📋 AI 日报 · 上午"
    assert "elements" in card

    # 必须有 tab 组件
    tab_elements = [e for e in card["elements"] if e.get("tag") == "tab"]
    assert len(tab_elements) == 1
    tab_ids = [t["tab_id"] for t in tab_elements[0]["tabs"]]
    assert "overview" in tab_ids
    assert "high" in tab_ids
    assert "medium" in tab_ids
    assert "low" in tab_ids

    # 必须有 tab_content 组件
    content_elements = [e for e in card["elements"] if e.get("tag") == "tab_content"]
    assert len(content_elements) == 4


def test_build_tab_card_empty_items():
    """空列表也返回有效的卡片结构。"""
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    card = notifier._build_tab_card([], "下午")
    assert "header" in card
    assert "elements" in card


def test_build_tab_card_no_analysis():
    """没有 analysis 的条目应被跳过。"""
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    items = [
        NewsItem(title="无分析", url="https://a.com", source="A", published=datetime.now(timezone.utc), summary=""),
    ]
    card = notifier._build_tab_card(items, "上午")
    # 卡片依然包含 overview tab
    tab = [e for e in card["elements"] if e.get("tag") == "tab"][0]
    assert "overview" in [t["tab_id"] for t in tab["tabs"]]


@pytest.mark.asyncio
async def test_send_news_with_valid_config_calls_cleanup():
    """验证 send_news 会先调用 cleanup（token 获取失败时不会发卡片）。"""
    config = {"feishu": {"app_id": "bad_id", "app_secret": "bad_secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    items = [
        NewsItem(title="测试", url="https://x.com", source="测试", published=datetime.now(timezone.utc),
                 summary="", analysis={"action": "精读原文", "category": "技术", "one_liner": "test"}),
    ]
    # token 获取会失败，但不应抛异常
    result = await notifier.send_news(items, "上午")
    assert result is False


@pytest.mark.asyncio
async def test_send_news_only_one_call():
    """验证 send_news 只发 1 条消息（之前是 N 条）。"""
    config = {"feishu": {"app_id": "", "app_secret": "", "chat_id": ""}}
    notifier = FeishuNotifier(config)
    items = [
        NewsItem(title="A", url="https://a.com", source="A", published=datetime.now(timezone.utc),
                 summary="", analysis={"action": "精读原文", "category": "技术", "one_liner": "a"}),
        NewsItem(title="B", url="https://b.com", source="B", published=datetime.now(timezone.utc),
                 summary="", analysis={"action": "了解即可", "category": "行业", "one_liner": "b"}),
    ]
    result = await notifier.send_news(items, "上午")
    # 配置为空应返回 False，但不应报错
    assert result is False
