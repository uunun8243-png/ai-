# AI 前沿新闻深度拆解系统

每日自动采集 AI 领域最新新闻，用 DeepSeek API 按 11 维度框架逐条深度分析，通过飞书群机器人推送到手机。

## 功能

- 自动采集 11 个数据源：Arxiv、GitHub Trending、Hacker News、Reddit r/MachineLearning、TechCrunch AI、量子位等中文科技媒体、Hugging Face、Meta AI、Google DeepMind、VentureBeat AI、AI Blog
- 指数半衰期新鲜度评分：按来源类型动态衰减（新闻6h/官方12h/学术48h），社区内容采用互动热度 Mode B
- AI 相关性过滤：自动识别并过滤与 AI 无关的新闻，确保推送内容聚焦 AI 领域
- 来源多样化排序：综合来源权重、时效性（指数衰减）、归一化热度、AI 关键词匹配度四维评分，阶梯跨源 boost
- 已发送状态追踪：自动记录已推送新闻，避免重复推送
- DeepSeek API 按 11 维度框架逐条深度分析
- 飞书群机器人推送，上午/下午各 15 条
- 运行质量自动检查：每次推送后自动验证6项质量指标（来源多样性、时效性、GitHub/Arxiv覆盖等）

## 快速开始

### 前置准备

1. **飞书开发者后台创建应用**
   - 访问 [飞书开发者平台](https://open.feishu.cn/app)
   - 创建企业自建应用（类型选「企业自建应用」）
   - 获取 **App ID** 和 **App Secret**
   - **不需要**发布或申请任何权限，机器人只需要发消息到群聊

2. **获取群聊 Chat ID**
   - 在飞书打开目标群 → 群设置 → 更多群信息
   - 复制底部的「群 ID」

3. **将机器人添加到群聊**
   - 在飞书开发者后台 → 应用功能 → 机器人 → 开启机器人
   - 在飞书搜索你的应用名称 → 添加到目标群聊

4. **DeepSeek API Key**
   - 访问 https://platform.deepseek.com/ 获取 API Key

### 部署

1. Fork 本仓库到你自己的 GitHub

2. 在 GitHub 仓库 Settings → Secrets and variables → Actions 添加：

   | Name | Value |
   |------|-------|
   | `FEISHU_APP_ID` | 你的飞书应用 App ID |
   | `FEISHU_APP_SECRET` | 你的飞书应用 App Secret |
   | `FEISHU_CHAT_ID` | 群聊的 Chat ID |
   | `DEEPSEEK_API_KEY` | 你的 DeepSeek API Key |

3. 启用 GitHub Actions
   - 到 Actions 标签页，确认 workflow 已启用
   - 可手动触发测试：Actions → AI News Daily Digest → Run workflow

4. 确认每天早上 8:00 和下午 14:00 自动推送

### 本地测试

```bash
cd news-digest
pip install -r requirements.txt
python -m src.main
```

### 配置项

编辑 `config.yaml` 可调整数据源开关、评分参数、推送数量等。

#### 分析 & 推送

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `analysis.max_news_per_day` | int | `15` | 每批最终推送的新闻数量 |
| `analysis.candidate_pool_size` | int | `45` | 候选池大小，先选出候选再精选 |
| `analysis.max_news_per_source` | int | `3` | 每个来源最多入选条数 |
| `analysis.recent_hours` | int | `24` | 默认新闻时效窗口（小时） |
| `analysis.source_recent_hours` | map | `{Arxiv: 72, GitHub: 96}` | 按源定制的时效窗口 |
| `analysis.require_ai_relevance` | bool | `true` | 是否开启 AI 相关性过滤 |
| `analysis.output_language` | str | `"zh-CN"` | 分析输出语言 |
| `analysis.source_limits` | map | 各源上限 | 每个来源在单批中的最大条数 |

#### 评分系统

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `scoring.weights.timeliness` | float | `0.30` | 时效性权重（最大因子） |
| `scoring.weights.source` | float | `0.15` | 来源权威度权重 |
| `scoring.weights.norm` | float | `0.15` | 热度归一化权重 |
| `scoring.weights.keyword` | float | `0.15` | AI 关键词匹配权重 |
| `scoring.freshness.half_life_news` | int | `6` | 新闻源半衰期（小时） |
| `scoring.freshness.half_life_official` | int | `12` | 官方源半衰期 |
| `scoring.freshness.half_life_academic` | int | `48` | 学术源半衰期 |
| `scoring.freshness.half_life_community` | int | `8` | 社区源半衰期（Mode B 衰减） |
| `scoring.freshness.engagement_window_hours` | int | `6` | 社区互动 Mode B 窗口 |
| `scoring.cross_source_boosts` | map | `{2: 0.05, 3: 0.10, 5: 0.20}` | 跨源覆盖阶梯加分 |
| `scoring.github.min_stars` | int | `300` | GitHub 仓库最低星数 |
| `scoring.github.time_window_days` | int | `7` | 搜索时间范围（天） |
| `scoring.github.query_keywords` | str | `"ai"` | GitHub 搜索关键词 |

## 项目结构

```
news-digest/
├── .github/workflows/daily-digest.yml  # GitHub Actions 配置
├── src/
│   ├── main.py           # 入口与流水线编排，含质量检查
│   ├── models.py         # NewsItem 数据模型
│   ├── aggregator.py     # AI 过滤/去重/评分/分批/跨源 boost
│   ├── sent_state.py     # 已发送追踪，防止重复推送
│   ├── analyzer.py       # DeepSeek API 分析
│   ├── collectors/       # 各数据源采集器
│   └── notifiers/        # 飞书推送
├── logs/test_runs/       # 每次运行的 JSON 日志（含 quality checks）
├── config.yaml           # 全局配置
├── requirements.txt
└── README.md
```

## 输出格式

每条新闻按 11 个维度分析：
1. **分类** — 技术创新/行业趋势/政策法规/产品发布/研究突破/融资动态
2. **一句话概述** — 谁+做了什么+关键数据
3. **背景** — 事件发生的上下文
4. **核心分析** — 根据新闻类型侧重点不同（技术解读/市场影响/功能亮点）
5. **为什么重要** — 对行业/技术/市场的影响
6. **学习价值** — 值得关注的技术点或行业认知
7. **应用实例** — 行业落地案例 + 学习应用建议
8. **行动建议** — 收藏/精读原文/动手实践/关注后续/了解即可
9. **趋势判断** — 短期热点/中期趋势/长期方向
10. **快速上手** — 技术/工具的体验方式
11. **一句话洞察** — 最值得记住的一个点
