# 飞书卡片折叠与自动清理设计

## 概述

对 AI 日报飞书推送进行两项改进：
1. **卡片折叠** — 将每批 10 张独立卡片合并为 1 张大卡片，用 Tab 按优先级分层展示
2. **自动清理** — 每次推送前自动清理 3 天前的机器人消息，减少群聊冗余

## 卡片折叠

### 消息结构

每批（上午/下午）发送 1 条飞书消息，使用飞书 Card Kit `tab` 组件。

### Tab 布局

| Tab 名称 | 内容 |
|----------|------|
| **📋 简报** | 所有新闻标题 + 优先级标签（🔴/🟡/🔵） + one_liner，列表形式 |
| **🔴 高 (N)** | action = "动手实践" / "精读原文" 的新闻，每条展示完整 10 字段分析 |
| **🟡 中 (N)** | action = "关注后续" / "收藏" 的新闻，每条展示完整 10 字段分析 |
| **🔵 低 (N)** | action = "了解即可" 的新闻，每条展示完整 10 字段分析 |

### 优先级推断规则

沿用现有逻辑，不修改 analyzer：

| action | 优先级 |
|--------|--------|
| 动手实践、精读原文 | 高 |
| 关注后续、收藏 | 中 |
| 了解即可 | 低 |

### Tab 内每条新闻的展示

和现有 `_build_card()` 内容完全一致：标题 header + 背景/核心分析/为什么重要/学习价值/快速上手 + 标签 + insight + 阅读原文按钮。

### 降级策略

如果飞书 Card Kit Tab 组件存在限制（如 tab 内不支持 button），则降级为 4 条消息方案：
- 1 条概览卡 + 3 条优先级分组卡（高/中/低各一条）

### 改动范围

- **feishu.py** — 重构 `send_news()` 方法，新增 Tab 卡片构建逻辑
- **feishu.py** — `_build_card()` 改为构建单条新闻在 tab 内的内联区块
- 其他文件不涉及

## 自动清理

### 流程

在 `send_news()` 推送新卡片**之前**，先调用 `_cleanup_old_messages()`：

1. 使用 `GET /im/v1/messages?container_id_type=chat&container_id={chat_id}&page_size=50` 获取机器人发送的消息列表
2. 遍历返回的消息，筛选 `send_time < now - 3 天` 的消息
3. 对每条匹配消息调用 `DELETE /im/v1/messages/{message_id}`

### 约束

- 只删除机器人自身发送的消息（飞书 API 限制）
- 3 天时间窗口从当前时间往前推，使用消息的 `send_time` 字段判断
- GitHub Actions 无状态环境，每次查询 API 获取消息列表，不依赖本地存储

### 改动范围

- **feishu.py** — 新增 `_cleanup_old_messages()` 私有方法
- **feishu.py** — 在 `send_news()` 开头调用该方法

## 不变的部分

- Analyzer 的 10 字段分析不变
- 优先级推断逻辑不变
- `send_alert()` 告警卡片不变
- Collector / Aggregator / Main pipeline 不变
- 配置项不变
