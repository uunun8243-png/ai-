# AI 变现项目日报设计

## 概述

在现有 AI 新闻日报系统中新增变现项目模块，每天随新闻推送 1-3 个 AI 变现项目（独立开发+创业方向），作为独立飞书卡片发送到同一群聊。

## 动机

现有系统每天推送 AI 前沿新闻，但缺少"如何用 AI 赚钱"的实操内容。增加变现项目栏目让读者从"看新闻"到"看机会"，提升信息实用价值。

## 数据来源

### 固定采集器（主要）

| 来源 | 采集方式 | 内容 | 优先级 |
|------|---------|------|--------|
| Product Hunt | RSS/API 或网页抓取 | 当日 Top AI 产品（标题、简介、点赞、链接） | P0 |
| IndieHackers | 网页抓取最新帖子 | 独立开发者收入报告、产品故事 | P0 |
| Reddit | RSS (r/SideProject, r/SaaS, r/Entrepreneur) | AI 工具晒收入、用户增长分享 | P1 |
| Hacker News | 已有采集器复用 | "Show HN" AI 产品 | P1 |
| GitHub Trending | 已有采集器复用 | 新型 AI 开源项目 | P2 |

### WebSearch 补充（兜底）

当固定采集器提供的新项目（未推送过的）不足 3 个时，触发 WebSearch 补充搜索，补齐至 3 个。搜索关键词动态构造，如 "AI tool revenue month"、"indie hacker AI product launch" 等。

## 数据模型

### MonetizationItem

```python
@dataclass
class MonetizationItem:
    title: str                # 项目名称
    url: str                  # 原文链接
    source: str               # 来源名称
    summary: str              # 原文摘要
    published: datetime       # 发布时间
    score: float = 0.0        # 热度/优先级评分
    analysis: Optional[dict] = None  # 变现分析结果
```

### 分析字段（DeepSeek prompt 产出）

| 字段 key | 说明 |
|----------|------|
| `one_liner` | 一句话概括项目核心卖点 |
| `business_model` | 商业模式分类（SaaS/订阅/买断/广告/抽成/开源+托管） |
| `revenue_estimate` | 收入估算（如 "月收入 $5K-10K"） |
| `target_users` | 目标用户群 |
| `tech_stack` | 技术栈/用到的 AI 技术 |
| `why_it_works` | 为什么能赚钱——核心洞察 |
| `china_adaptation` | 国内借鉴/可复制性分析 |
| `action` | 行动建议（想复刻的第一步） |

## 去重策略

复用 `SentState` 机制，但使用独立的去重键前缀 `monetization:`，与新闻去重隔离。

- 去重依据：项目 URL
- 保留时间：30 天（变现项目回溯窗口比新闻长）

## 评分与选品

由于每日仅需 1-3 个项目，使用简化评分：

```
score = source_boost(来源权重) + 热度(点赞/评论归一化) + 新鲜度(指数衰减)
```

按 score 降序取前 3，已推送过的跳过。

来源权重：ProductHunt 1.0, IndieHackers 1.0, Reddit 0.8, HN 0.7, WebSearch 0.6

## 推送格式

独立的飞书消息卡片，header 为 "💰 AI 变现项目 · 上午/下午"，不混入新闻卡片。

每个项目展示：
- 标题 + 一句话概括
- 商业模式 / 收入估算 / 目标用户 / 技术栈（关键指标一行一个）
- 为什么能赚钱（一段核心洞察）
- 国内借鉴（一段分析）
- 行动建议 + 查看原文按钮

## 配置文件

在 `config.yaml` 新增 `monetization` 节：

```yaml
monetization:
  enabled: true
  max_per_day: 3
  sources:
    product_hunt: true
    indie_hackers: true
    reddit: true
  websearch_fallback: true
  sent_state_retention_days: 30
  source_weights:
    Product Hunt: 1.0
    IndieHackers: 1.0
    Reddit: 0.8
    Hacker News: 0.7
    GitHub Trending: 0.6
```

## 流水线集成

在 `main.py` 现有新闻流水线后追加：

1. `collect_monetization()` — 调用各采集器
2. `filter_sent_monetization()` — 过滤已推送项目
3. `analyze_monetization()` — DeepSeek 分析（使用专用 prompt）
4. `send_monetization()` — 推送独立飞书卡片

如果变现项目不足 1 个，跳过推送，不阻塞新闻主流程。

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/collectors/monetization_collector.py` | 新增 | ProductHunt + IndieHackers + Reddit 采集器 |
| `src/collectors/__init__.py` | 修改 | 注册新采集器 |
| `src/monetization_analyzer.py` | 新增 | 专用分析 prompt + 逻辑（或复用 Analyzer 加参数） |
| `src/notifiers/feishu.py` | 修改 | 新增 `send_monetization()` 卡片方法 |
| `src/main.py` | 修改 | 新增 monetization 流水线阶段 |
| `src/sent_state.py` | 修改 | 支持 monetization 独立去重 |
| `src/models.py` | 修改 | 新增 MonetizationItem（或复用 NewsItem） | 复用 NewsItem 简化实现 |
| `config.yaml` | 修改 | 新增 monetization 配置节 |

## 错误处理

- 采集失败 → 记日志，不阻塞主新闻推送
- 分析失败 → 该条跳过，尝试下一条
- 全部失败 → 跳过推送，静默失败
- 任何阶段异常 → 不影响现有新闻流水线

## 质量目标

- 单次执行确保 ≥1 个项目推送（数据充足时）
- 项目 7 天内不重复推送
- 卡片渲染后能在飞书群清晰阅读
