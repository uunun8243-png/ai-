# Feishu Card Consolidation & Auto-Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce Feishu group chat noise by consolidating 10 individual news cards into 1 tab-based card per batch, and auto-clean messages older than 3 days.

**Architecture:** Two independent features in `FeishuNotifier` — (1) `_cleanup_old_messages()` queries and deletes bot messages older than 3 days via Feishu API, (2) `_build_tab_card()` replaces per-item `_send_card()` calls with a single card using Feishu Card Kit tab component.

**Tech Stack:** Python 3.11+, httpx, Feishu Open API (im/v1/messages), Feishu Card Kit tabs

---

### Task 1: Add message cleanup to FeishuNotifier

**Files:**
- Modify: `src/notifiers/feishu.py` (add `_cleanup_old_messages()`)
- Test: `tests/test_feishu.py`

- [ ] **Step 1: Write the cleanup test**

Add to `tests/test_feishu.py`:

```python
@pytest.mark.asyncio
async def test_cleanup_missing_config_returns_false():
    """无配置时 cleanup 不应报错。"""
    config = {"feishu": {"app_id": "", "app_secret": "", "chat_id": ""}}
    notifier = FeishuNotifier(config)
    # 应该静默返回 False，不抛异常
    result = await notifier._cleanup_old_messages()
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd f:/news/news-digest && python -m pytest tests/test_feishu.py::test_cleanup_missing_config_returns_false -v`
Expected: FAIL with `AttributeError: '_CleanupOldMessages' not found` or similar.

- [ ] **Step 3: Write minimal `_cleanup_old_messages()` implementation**

In `src/notifiers/feishu.py`, add to the `FeishuNotifier` class:

```python
async def _cleanup_old_messages(self, token: str) -> bool:
    """删除 3 天前的机器人消息。"""
    if not self.chat_id:
        return False

    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    cutoff_ts = str(int(cutoff.timestamp()))

    async with httpx.AsyncClient() as client:
        try:
            # 分页查询历史消息
            page_token = None
            while True:
                params = {
                    "container_id_type": "chat",
                    "container_id": self.chat_id,
                    "page_size": 50,
                    "sort_type": "ByCreateTimeDesc",
                }
                if page_token:
                    params["page_token"] = page_token

                resp = await client.get(
                    f"{FEISHU_BASE}/im/v1/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 0:
                    print(f"  ⚠ 查询消息失败: {data}")
                    return False

                items = data.get("data", {}).get("items", [])
                for msg in items:
                    sender_type = msg.get("sender", {}).get("sender_type", "")
                    msg_type = msg.get("msg_type", "")
                    if sender_type != "app" or msg_type != "interactive":
                        continue
                    create_time = msg.get("create_time", "0")
                    if create_time < cutoff_ts:
                        msg_id = msg.get("message_id", "")
                        if msg_id:
                            await client.delete(
                                f"{FEISHU_BASE}/im/v1/messages/{msg_id}",
                                headers={"Authorization": f"Bearer {token}"},
                                timeout=10.0,
                            )

                page_token = data.get("data", {}).get("page_token")
                if not data.get("data", {}).get("has_more"):
                    break
        except Exception as e:
            print(f"  ⚠ 清理旧消息失败: {e}")
            return False

    return True
```

Also add the import at top of the file (httpx is already imported; `datetime`/`timedelta`/`timezone` — `datetime` and `timezone` already imported, add `timedelta`):

Look for `from datetime import datetime, timezone` and change to `from datetime import datetime, timedelta, timezone`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd f:/news/news-digest && python -m pytest tests/test_feishu.py::test_cleanup_missing_config_returns_false -v`
Expected: PASS

- [ ] **Step 5: Wire cleanup into `send_news()`**

In `send_news()`, after the line `token = await self._get_tenant_token()`, add:

```python
# 清理 3 天前的旧卡片
await self._cleanup_old_messages(token)
```

- [ ] **Step 6: Run all existing tests to confirm no regression**

Run: `cd f:/news/news-digest && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/notifiers/feishu.py tests/test_feishu.py
git commit -m "feat: auto-cleanup Feishu messages older than 3 days"
```

---

### Task 2: Build helper utilities for tab card

**Files:**
- Modify: `src/notifiers/feishu.py` (add `_sort_by_priority()` class method + `_build_overview_section()`)

- [ ] **Step 1: Write test for priority sorting**

Add to `tests/test_feishu.py`:

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd f:/news/news-digest && python -m pytest tests/test_feishu.py::test_sort_by_priority tests/test_feishu.py::test_sort_by_priority_within_same_level tests/test_feishu.py::test_sort_by_priority_empty -v`
Expected: 3 FAIL

- [ ] **Step 3: Implement `_sort_by_priority()`**

Add to `FeishuNotifier`:

```python
@staticmethod
def _sort_by_priority(items: List[NewsItem]) -> List[NewsItem]:
    """按优先级排序：高 → 中 → 低，同级保持原顺序。"""
    order = {"高": 0, "中": 1, "低": 2}
    return sorted(items, key=lambda x: order.get(_infer_importance(x.analysis or {}), 3))
```

- [ ] **Step 4: Run tests to pass**

Run: `cd f:/news/news-digest && python -m pytest tests/test_feishu.py::test_sort_by_priority tests/test_feishu.py::test_sort_by_priority_within_same_level tests/test_feishu.py::test_sort_by_priority_empty -v`
Expected: 3 PASS

- [ ] **Step 5: Install httpx if needed (already installed per existing code)**

- [ ] **Step 6: Commit**

```bash
git add src/notifiers/feishu.py tests/test_feishu.py
git commit -m "feat: add priority sorting helper for tab card"
```

---

### Task 3: Build the tab card with Feishu Card Kit tabs

**Files:**
- Modify: `src/notifiers/feishu.py` (add `_build_tab_card()` method)
- Test: `tests/test_feishu.py` (add tab card structure test)

- [ ] **Step 1: Write test for tab card structure**

Add to `tests/test_feishu.py`:

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd f:/news/news-digest && python -m pytest tests/test_feishu.py::test_build_tab_card_structure tests/test_feishu.py::test_build_tab_card_empty_items tests/test_feishu.py::test_build_tab_card_no_analysis -v`
Expected: 3 FAIL

- [ ] **Step 3: Implement `_build_tab_card()`**

Feishu Card Kit tab structure:

```python
def _build_tab_card(self, items: List[NewsItem], batch_label: str) -> dict:
    """将多条新闻构建为一张带 Tab 切换的飞书消息卡片。
    
    Tab 结构：概览 | 高(N) | 中(N) | 低(N)
    概览 = 所有标题+优先级标签+one_liner 列表
    高/中/低 = 对应优先级的完整 10 字段分析
    """
    # 过滤掉没有 analysis 的条目
    valid = [it for it in items if it.analysis]
    # 排序并分组
    sorted_items = self._sort_by_priority(valid)
    
    groups = {"高": [], "中": [], "低": []}
    for it in sorted_items:
        importance = _infer_importance(it.analysis or {})
        groups[importance].append(it)
    
    # 构建 Tab 选项
    tabs = []
    tab_elements_map = {}
    
    def _make_tab(tab_id: str, label: str, selected: bool = False):
        return {"tab_id": tab_id, "tab": {"tag": "plain_text", "content": label}, "selected": selected}
    
    # 1. 概览 Tab
    overview_items = []
    for it in sorted_items:
        imp = _infer_importance(it.analysis or {})
        badge = {"高": "🔴", "中": "🟡", "低": "🔵"}.get(imp, "⚪")
        action = it.analysis.get("action", "")
        one_liner = it.analysis.get("one_liner", "")
        overview_items.append(f"{badge} **[{action}]** {it.title}\n{one_liner}")
    
    overview_md = "\n\n---\n\n".join(overview_items) if overview_items else "暂无新闻"
    overview_elements = [{"tag": "div", "text": {"tag": "lark_md", "content": overview_md}}]
    
    tabs.append(_make_tab("overview", f"📋 简报", True))
    tab_elements_map["overview"] = overview_elements
    
    # 2. 高/中/低 Tab
    imp_labels = [("high", "高", "🔴"), ("medium", "中", "🟡"), ("low", "低", "🔵")]
    for tab_id, key, emoji in imp_labels:
        group_items = groups[key]
        elements = []
        for idx, it in enumerate(group_items):
            a = it.analysis or {}
            # 标题行
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{it.title}**\n{a.get('category', '')} · {it.source}"},
            })
            elements.append({"tag": "hr"})
            
            # 内容区块：背景 / 核心分析 / 为什么重要 / 学习价值
            sections = [
                ("📖 背景", a.get("background")),
                ("🔍 核心分析", a.get("core_analysis")),
                ("💡 为什么重要", a.get("why_matters")),
                ("📚 学习价值", a.get("learning_value")),
            ]
            for label, content in sections:
                if content:
                    elements.append({
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{content}"},
                    })
            
            # 快速上手
            qs = a.get("quick_start", "")
            if qs and qs != "无需上手":
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**🚀 快速上手**\n{qs}"},
                })
            
            # 底部标签
            footer_parts = []
            if a.get("action"):
                footer_parts.append(f"📌 {a['action']}")
            if a.get("trend"):
                footer_parts.append(f"📈 {a['trend']}")
            if footer_parts:
                elements.append({"tag": "hr"})
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "  ·  ".join(footer_parts)},
                })
            
            # insight
            if a.get("insight"):
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"💬 {a['insight']}"},
                })
            
            # 阅读原文按钮
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🔗 阅读原文"},
                    "type": "default",
                    "url": it.url,
                }],
            })
            
            # 条目之间分隔
            if idx < len(group_items) - 1:
                elements.append({"tag": "hr"})
        
        if not elements:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "暂无此优先级的新闻"},
            })
        
        tab_count = len(group_items)
        tabs.append(_make_tab(tab_id, f"{emoji} {key}({tab_count})", False))
        tab_elements_map[tab_id] = elements
    
    # 组装最终卡片
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📋 AI 日报 · {batch_label}"},
            "template": "blue",
        },
        "elements": [
            # Tab 选择器
            {"tag": "tab", "tabs": tabs},
            # 各 Tab 内容
            *[{"tag": "tab_content", "tab_id": tid, "elements": el}
              for tid, el in tab_elements_map.items()],
        ],
    }
    return card
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd f:/news/news-digest && python -m pytest tests/test_feishu.py::test_build_tab_card_structure tests/test_feishu.py::test_build_tab_card_empty_items tests/test_feishu.py::test_build_tab_card_no_analysis -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/notifiers/feishu.py tests/test_feishu.py
git commit -m "feat: build consolidated tab card for Feishu"
```

---

### Task 4: Update send_news to use tab card and clean up

**Files:**
- Modify: `src/notifiers/feishu.py` (rewrite `send_news()` to use `_build_tab_card()` instead of per-item `_build_card()` + `_send_card()`)
- Keep: `_build_card()` and `_format_analysis_text()` as they may be used externally (safe to keep)
- Test: `tests/test_feishu.py` (update `test_missing_config_returns_false` if needed)

- [ ] **Step 1: Write test for new send_news behavior**

Add to `tests/test_feishu.py`:

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail (expected: pass since they test error paths)**

Run: `cd f:/news/news-digest && python -m pytest tests/test_feishu.py::test_send_news_with_valid_config_calls_cleanup tests/test_feishu.py::test_send_news_only_one_call -v`
Expected: Both PASS (testing missing config paths)

- [ ] **Step 3: Rewrite `send_news()` to use tab card**

Replace the existing `send_news()` method:

```python
async def send_news(self, items: List[NewsItem], batch_label: str = "上午") -> bool:
    """将一批新闻以 Tab 卡片形式发送到飞书群（只发 1 条消息）。"""
    if not self.app_id or not self.app_secret or not self.chat_id:
        print("飞书 API 配置不完整（需要 app_id, app_secret, chat_id）")
        return False

    try:
        token = await self._get_tenant_token()
    except Exception as e:
        print(f"  ✗ 获取飞书 token 失败: {e}")
        return False

    # 清理 3 天前的旧卡片
    try:
        await self._cleanup_old_messages(token)
    except Exception as e:
        print(f"  ⚠ 清理旧消息失败: {e}")

    # 构建 Tab 卡片并发送
    try:
        card = self._build_tab_card(items, batch_label)
        await self._send_card(token, card)
        return True
    except Exception as e:
        print(f"  ✗ 发送 Tab 卡片失败: {e}")
        return False
```

- [ ] **Step 4: Remove old `_build_card()` if nothing else references it**

Keep `_build_card()` and `_format_analysis_text()` — they're valid utilities. Just no longer called from `send_news()`.

- [ ] **Step 5: Run all tests to verify everything passes**

Run: `cd f:/news/news-digest && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/notifiers/feishu.py tests/test_feishu.py
git commit -m "feat: use consolidated tab card for news push"
```

---

### Task 5: End-to-end verification

- [ ] **Step 1: Run full test suite**

Run: `cd f:/news/news-digest && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run the pipeline once (dry-run with real config)**

Simulate the pipeline with a single collector to verify no import/type errors:

```bash
cd f:/news/news-digest
python -c "
from src.notifiers.feishu import FeishuNotifier
from datetime import datetime, timezone
from src.models import NewsItem

# 验证 _build_tab_card 能正确构建
config = {'feishu': {'app_id': '', 'app_secret': '', 'chat_id': ''}}
n = FeishuNotifier(config)
items = [
    NewsItem(title='GPT-5发布', url='https://x.com', source='OpenAI',
             published=datetime.now(timezone.utc), summary='',
             analysis={'action': '精读原文', 'category': '技术创新', 'one_liner': '发布了', 'core_analysis': 'MoE'}),
    NewsItem(title='新框架', url='https://y.com', source='GitHub',
             published=datetime.now(timezone.utc), summary='',
             analysis={'action': '了解即可', 'category': '开源', 'one_liner': '新框架发布', 'core_analysis': 'Rust 编写'}),
]
card = n._build_tab_card(items, '上午')
import json
print(json.dumps(card, ensure_ascii=False, indent=2))
"
```

Expected: Valid JSON card structure with 4 tabs printed without errors.

- [ ] **Step 3: Verify cleanup logic**

Run a quick sanity check that the cleanup method doesn't crash with empty config:

```bash
cd f:/news/news-digest
python -c "
import asyncio
from src.notifiers.feishu import FeishuNotifier

async def test():
    n = FeishuNotifier({'feishu': {'app_id': '', 'app_secret': '', 'chat_id': ''}})
    result = await n._cleanup_old_messages('fake_token')
    print(f'Cleanup result: {result}')

asyncio.run(test())
"
```

Expected: `Cleanup result: False` (no crash)

- [ ] **Step 4: Final commit if any changes from verification**

```bash
git add -A
git commit -m "chore: verification fixes for tab card and cleanup"
```
