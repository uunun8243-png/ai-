# 飞书卡片新增"应用实例"字段与布局优化设计

## 概述

在现有飞书优先级卡片基础上进行两项优化：
1. **新增"应用实例"字段** — Analyzer 输出第11个分析维度
2. **移除简报概览区块** — 将简报信息合并到每篇文章标题行，使布局更紧凑

## 分析器变更

### 新增字段

在 `src/analyzer.py` 的 `ANALYSIS_PROMPT` 中，于 `learning_value` 与 `action` 之间插入：

```json
"application_example": "应用实例：该技术/新闻在行业的实际落地案例（谁在用、用来解决什么问题）+ 读者可以如何将这一知识应用到自己的项目或学习中"
```

字段位置：
```
learning_value → application_example（新增） → action（原顺序不变）
```

### 改动范围

- **src/analyzer.py** — prompt 插入新字段定义
- 无需修改 response_format 或其他逻辑

## 卡片布局变更

### 删除简报区块

去掉 `_build_priority_card()` 中的独立 📋 简报概览 div，改为在每篇文章标题行直接展示。

### 每篇文章标题行

改前：
```
**{title}**
{category} · {source}
```

改后：
```
🔴/🟡/🔵 [{action}] {title} — {one_liner}
{category} · {source}
```

### 新增应用实例渲染

在每篇文章的区块中，于 `📚 学习价值` 之后、`🚀 快速上手` 之前插入：

```
💡 应用实例
{application_example}
```

### 卡片结构完整示意

```
📋 AI 日报 · 上午

🔴 高（N 条）
━━━━━━━━━━━━━━━━━━━━━━━━
🔴 [精读原文] 标题 — one_liner
类别 · 来源

📖 背景
...
🔍 核心分析
...
💡 为什么重要
...
📚 学习价值
...
💡 应用实例          ← 新增
...
🚀 快速上手（如果有）
📌 action · 📈 趋势
💬 insight
🔗 阅读原文

━━━━━━━━━━━━━━━━━━━━━━━━
...更多文章...

🟡 中（N 条）
...
🔵 低（N 条）
...
```

### 改动范围

- **src/notifiers/feishu.py** — 修改 `_build_priority_card()` 方法
- **tests/test_feishu.py** — 更新测试数据（添加 application_example，更新标题行断言）

## 不变的部分

- 排序逻辑（高→中→低）、优先级推断逻辑不变
- cleanup 逻辑、send_news 流程不变
- 其他通知渠道不变
- 配置项不变
- NewsItem 模型不变（analysis 仍是 dict）
