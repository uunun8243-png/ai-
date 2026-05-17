# 评分体系重构 & 新鲜度重新设计

**日期**: 2026-05-17
**分支**: fix/github-search-422
**状态**: 待实现

## 问题诊断

| 问题 | 根因 |
|------|------|
| GitHub Trending = 0 条 | 查询条件过严：`topic:ai/topic:llm/topic:machine-learning` 大部分仓库不设 Topics，`stars:>1000` + 7d 窗口结果极少 |
| Arxiv 不上榜 | 学术论文标题不含 AI 热词（LLM/agent），keyword_signal 低，总分拼不过科技媒体 |
| 重复推送旧内容 | `recent_hours=24` 窗口太宽，热门内容在 feed 中存活一整天，每次采集相同条目、相同排名，被 sent-state 全部过滤 |
| 时效性评分不对 | 线性衰减 `1 - age/24` 导致 12h 前的内容仍有 50% 新鲜度，新内容与旧内容区分不足 |

## 设计

### 1. 时效性信号（替换线性衰减）

按来源类型采用两种模式：

**模式 A：纯时间衰减**（新闻媒体/官方/学术）

```
timeliness = e^(-age_hours / half_life)
```

| 来源类型 | 半衰期 | 说明 |
|---------|-------|------|
| 新闻媒体（TechCrunch、VentureBeat AI、中文科技媒体、AI Blog） | 6h | 快节奏新闻 |
| 官方来源（OpenAI、Anthropic、DeepMind、Meta AI、Google AI、Hugging Face） | 12h | 官方公告影响更持久 |
| 学术（Arxiv） | 48h | 论文生命周期长 |

**模式 B：互动热度**（社区源：HN、Reddit）

```
timeliness = log(score + 1) × e^(-age_hours / decay_half_life)
          （仅 age_hours <= 6h 时计算互动分量）

6h 内：互动热度决定
6-24h：降级为纯时间衰减，半衰期 8h
24h+：filter_recent 过滤
```

- `score` = HN points / Reddit upvotes
- `decay_half_life` = 6h（互动热度窗口内的时间衰减）
- 8h 前 500 分的帖子 > 2h 前 5 分的帖子（互动速度 = 真正热度）

### 2. 排名公式权重调整

```
总分 = source_signal    × 0.15        （来源权威，从 0.25 降）
     + timeliness       × 0.30        （时效/热度，从 0.25 升）
     + norm_signal      × 0.15        （同源内相对排名，从 0.20 降）
     + keyword_signal   × 0.15        （关键词匹配，不变）
     + cross_source_boost              （跨源覆盖，阶梯加分）
     + release_boost                   （官方发布加分，不变）
```

核心变化：timeliness 权重 0.30 成为最大因子，来源权重降低——热度比出处更重要。

### 3. 跨源覆盖 boost（改进 burst_detect）

阶梯加分替代二元 boost：

| 覆盖来源数 | boost |
|-----------|-------|
| 2 | +0.05 |
| 3 | +0.10 |
| 4 | +0.15 |
| 5+ | +0.20 |

### 4. GitHub 查询修复

```
# 旧
stars:>1000 created:>=YYYY-MM-DD (ai OR llm OR generative OR topic:ai OR topic:llm OR topic:machine-learning)

# 新
stars:>=300 created:>=YYYY-MM-DD ai
```

- 去掉所有 `topic:` 限定
- 门槛降到 `stars:>=300`
- 关键词精简为 `ai`（GitHub 搜索匹配 description + readme + topics）
- 如果仍偏少，时间窗拉长到 14d 或门槛降到 100

### 5. Arxiv 学术关键词

新增学术架构/技术关键词表，用于 keyword_signal 计算：

**架构类**: transformer, diffusion model, Mamba, SSM, state space model, MoE, mixture of experts, attention mechanism, encoder-decoder, autoregressive, graph neural network, normalization, embedding, residual, convolution, self-attention, cross-attention

**训练/优化**: fine-tuning, RLHF, DPO, reinforcement learning from human feedback, distillation, quantization, pruning, LoRA, adapter, curriculum learning, contrastive learning, self-supervised

**推理/效率**: speculative decoding, KV cache, flash attention, sparse, low-rank, mixture, efficient, inference optimization, chain-of-thought, CoT

**新方法信号**: novel, state-of-the-art, SOTA, framework, outperforms, first, new architecture, new method, propose, introduce

Arxiv keyword_signal = min(命中数 / 3, 1.0)

两套关键词表（通用 AI 关键词 + 学术关键词）合并计算，确保学术论文也能得分。

### 6. Reddit 采集器补充 score

Reddit 采集器改用 JSON API（`.json` 端点）替代 RSS，采集 `score` 和 `num_comments` 字段。URL 格式：
```
https://www.reddit.com/r/MachineLearning/hot.json?limit=15
```

### 7. 所有参数可配置

在 `config.yaml` 中新增 `scoring` 节：

```yaml
scoring:
  freshness:
    half_life_news: 6
    half_life_official: 12
    half_life_academic: 48
    half_life_community: 8
    engagement_window_hours: 6
  weights:
    source: 0.15
    timeliness: 0.30
    norm: 0.15
    keyword: 0.15
  cross_source_boosts:
    2: 0.05
    3: 0.10
    4: 0.15
    5: 0.20
  github:
    min_stars: 300
    time_window_days: 7
    query_keywords: "ai"
  arxiv:
    max_papers_per_category: 20
```

## 测试方案

### 测试脚本 `scripts/test_pipeline.ps1`

- 每 2 小时运行一次 `python -m src.main`
- 每次运行记录到 `logs/test_runs/YYYY-MM-DD-HHmmss.json`
- 记录内容：采集数量（按来源）、排名榜单（含分数明细）、推送内容、sent-state 过滤数

### 输出质量评判标准

每次运行输出需包含：

1. **来源多样性**: 10 条结果中至少覆盖 3 个不同来源
2. **时效性**: 至少 50% 的条目发布时间在 6h 内
3. **GitHub 恢复**: GitHub 采集数 > 0
4. **Arxiv 上榜**: 至少 1 篇 Arxiv 论文进入前 10
5. **新内容率**: 每次推送中 > 50% 为首次出现（未被 sent-state 过滤）
6. **跨源热点**: 如有 3+ 源覆盖的事件，必须上榜

### 调参流程

1. 修改 `config.yaml` 中的参数
2. 等待 2h 定时触发或手动运行
3. 对比输出记录与评判标准
4. 重复直到所有标准满足
