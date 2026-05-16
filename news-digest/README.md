# AI 前沿新闻深度拆解系统

每日自动采集 AI 领域最新新闻，用 DeepSeek API 按 11 维度框架逐条深度分析，通过飞书群机器人推送到手机。

## 功能

- 自动采集 9 个数据源：Arxiv、GitHub Trending、Hacker News、OpenAI/Anthropic/Google AI Blog、Reddit、机器之心、量子位
- 去重排序，每日精选 10+ 条核心新闻
- DeepSeek API 按 11 维度框架逐条深度分析
- 飞书群机器人推送，上午/下午两批发送

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

编辑 `config.yaml` 可调整数据源开关、分析数量等。

## 项目结构

```
news-digest/
├── .github/workflows/daily-digest.yml  # GitHub Actions 配置
├── src/
│   ├── main.py           # 入口与流水线编排
│   ├── models.py         # NewsItem 数据模型
│   ├── aggregator.py     # 去重/排序/分批
│   ├── analyzer.py       # DeepSeek API 分析
│   ├── collectors/       # 各数据源采集器
│   └── notifiers/        # 飞书推送
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
