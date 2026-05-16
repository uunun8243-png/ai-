# 应用实例字段与卡片布局优化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Analyzer 输出中新增第11个字段"应用实例"，并在飞书优先级卡片中渲染该字段；同时移除独立的简报概览区块，将优先级/action/one_liner 合并到文章标题行。

**Architecture:** 三个独立改动：① analyzer prompt 插入新字段定义；② `_build_priority_card()` 改标题行 + 移除简报区块 + 新增 application_example 渲染；③ 更新测试数据和断言。

**Tech Stack:** Python, DeepSeek API, Feishu Card Kit

---

### Task 1: Analyzer prompt 新增 application_example 字段

**Files:**
- Modify: `src/analyzer.py:13-24`

- [ ] **Step 1: 在 prompt 中插入新字段**

在 `learning_value` 和 `action` 之间插入 `application_example`：

```python
# 改前 (learning_value 之后直接是 action):
"learning_value": "作为学习者能从中获得什么...",
"action": "建议行动：收藏|精读原文|...",

# 改后:
"learning_value": "作为学习者能从中获得什么...",
"application_example": "应用实例：该技术/新闻在行业的实际落地案例（谁在用、用来解决什么问题）+ 读者可以如何将这一知识应用到自己的项目或学习中",
"action": "建议行动：收藏|精读原文|...",
```

- [ ] **Step 2: 验证无语法错误**

Run: `python -c "import ast; ast.parse(open('src/analyzer.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/analyzer.py
git commit -m "feat: add application_example field to analyzer prompt"
```

---

### Task 2: 更新飞书卡片布局

**Files:**
- Modify: `src/notifiers/feishu.py:41-164`
- Test: `tests/test_feishu.py`

- [ ] **Step 1: 更新测试 — 修改 test_build_priority_card_structure 移除简报断言 + 新增 application_example 测试**

将 `test_build_priority_card_structure` 的断言从检查"📋 简报"改为检查标题行包含优先级标记 + action + one_liner，并验证 application_example 出现在元素中。

```python
def test_build_priority_card_structure():
    """卡片必须包含 高/中/低 三个分区和 application_example 字段。"""
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    items = [
        NewsItem(title="高优先级新闻", url="https://a.com", source="测试", published=datetime.now(timezone.utc), summary="",
                 analysis={"category": "技术创新", "one_liner": "一条高优先级", "action": "精读原文", "trend": "中期趋势",
                           "application_example": "可以尝试用 MoE 架构重训分类模型"}),
        NewsItem(title="低优先级新闻", url="https://b.com", source="测试", published=datetime.now(timezone.utc), summary="",
                 analysis={"category": "行业趋势", "one_liner": "一条低优先级", "action": "了解即可"}),
    ]
    card = notifier._build_priority_card(items, "上午")
    assert "header" in card
    assert card["header"]["title"]["content"] == "📋 AI 日报 · 上午"
    assert "elements" in card
    # 检查标题行包含优先级标记和 one_liner（不应再有独立"📋 简报"）
    div_texts = [e["text"]["content"] for e in card["elements"] if e.get("tag") == "div" and e.get("text", {}).get("tag") == "lark_md"]
    assert any("🔴" in t and "[精读原文]" in t and "一条高优先级" in t for t in div_texts), "标题行应包含优先级标记 + action + one_liner"
    assert any("🔵" in t and "[了解即可]" in t and "一条低优先级" in t for t in div_texts)
    assert any("🔴 高" in t for t in div_texts), "缺少高优先级分区"
    assert any("🟡 中" in t for t in div_texts), "缺少中优先级分区"
    assert any("🔵 低" in t for t in div_texts), "缺少低优先级分区"
    # 检查 application_example 出现在元素中
    assert any("应用实例" in t for t in div_texts)
```

- [ ] **Step 2: 更新测试 — 修改 test_build_priority_card_no_analysis 移除简报引用**

```python
def test_build_priority_card_no_analysis():
    """没有 analysis 的条目应被跳过。"""
    config = {"feishu": {"app_id": "id", "app_secret": "secret", "chat_id": "chat"}}
    notifier = FeishuNotifier(config)
    items = [
        NewsItem(title="无分析", url="https://a.com", source="A", published=datetime.now(timezone.utc), summary=""),
    ]
    card = notifier._build_priority_card(items, "上午")
    div_texts = [e["text"]["content"] for e in card["elements"] if e.get("tag") == "div" and e.get("text", {}).get("tag") == "lark_md"]
    # 没有有效条目时显示"暂无新闻"
    assert any("暂无新闻" in t for t in div_texts)
```

- [ ] **Step 3: 运行测试验证失败**

Run: `pytest tests/test_feishu.py -v`
Expected: test_build_priority_card_structure 和 test_build_priority_card_no_analysis 失败（因为卡片布局已改但代码未改）

- [ ] **Step 4: 修改 _build_priority_card — 移除简报概览区块**

删除 `_build_priority_card()` 中约第60-77行的独立简报区块：

```python
# ── 删除整个简报概览区块 ──
# if sorted_items:
#     overview_lines = []
#     for it in sorted_items:
#         ...
#     elements.append({...})
# else:
#     elements.append({...})
```

保留 else 分支的"暂无新闻"处理，移到分区逻辑之前：

```python
elements = []

# 如果没有有效条目，直接显示暂无新闻并返回
if not sorted_items:
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": "本次暂无新闻"},
    })
    # 仍然返回完整的卡片结构
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📋 AI 日报 · {batch_label}"},
            "template": "blue",
        },
        "elements": elements,
    }
```

- [ ] **Step 5: 修改 _build_priority_card — 标题行合并显示优先级 + action + one_liner**

将每篇文章的标题 div（当前第98-101行）从：

```python
elements.append({
    "tag": "div",
    "text": {"tag": "lark_md", "content": f"**{it.title}**\n{a.get('category', '')} · {it.source}"},
})
```

改为：

```python
imp = _infer_importance(it.analysis or {})
badge = {"高": "🔴", "中": "🟡", "低": "🔵"}.get(imp, "⚪")
action_label = a.get("action", "")
one_liner = a.get("one_liner", "")
title_line = f"{badge} **[{action_label}]** {it.title}"
if one_liner:
    title_line += f" — {one_liner}"
elements.append({
    "tag": "div",
    "text": {"tag": "lark_md", "content": f"{title_line}\n{a.get('category', '')} · {it.source}"},
})
```

注意：这里每篇文章循环内已经能拿到 `it.analysis`，但需要从外层拿到 `_infer_importance` 的结果。当前第55行 `importance = _infer_importance(it.analysis or {})` 已经计算了优先级，可以复用。

实际上，当前代码中第96行的 `for idx, it in enumerate(group_items):` 在每个 priority group 内循环，此时我们已经知道 `key`（即优先级字符串），所以可以直接用 `key` 来获取 badge。但为了更清晰，可以继续用 `_infer_importance`。

让我改用更简洁的方式——注意在 groups 循环内，`key` 已经是优先级字符串了（"高"/"中"/"低"），所以：

```python
badge = {"高": "🔴", "中": "🟡", "低": "🔵"}.get(key, "⚪")
```

- [ ] **Step 6: 修改 _build_priority_card — 新增 application_example 渲染**

在"学习价值"区块之后、"快速上手"之前，插入 application_example 渲染：

```python
# 在 sections 列表最后追加 application_example
sections = [
    ("📖 背景", a.get("background")),
    ("🔍 核心分析", a.get("core_analysis")),
    ("💡 为什么重要", a.get("why_matters")),
    ("📚 学习价值", a.get("learning_value")),
    ("💡 应用实例", a.get("application_example")),   # ← 新增
]
```

这样 application_example 如果有值就会自动渲染，没值则跳过（has_content 逻辑自动处理）。

- [ ] **Step 7: 运行测试验证全部通过**

Run: `pytest tests/test_feishu.py -v`
Expected: 所有测试 PASS

- [ ] **Step 8: 运行全量测试**

Run: `pytest -v`
Expected: 全部 37+ 测试 PASS

- [ ] **Step 9: Commit**

```bash
git add src/notifiers/feishu.py tests/test_feishu.py
git commit -m "feat: merge briefing into title, add application_example to card"
```
