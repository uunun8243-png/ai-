# AI 前沿新闻深度拆解系统

每日自动采集 AI 领域最新新闻，用 DeepSeek API 按 10 维度框架逐条深度分析，通过飞书群机器人推送到手机。

## 功能

- 自动采集 9 个数据源：Arxiv、GitHub Trending、Hacker News、OpenAI/Anthropic/Google AI Blog、Reddit、机器之心、量子位
- 去重排序，每日精选 10+ 条核心新闻
- DeepSeek API 按 10 维度框架逐条深度分析
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

每条新闻按 10 个维度分析：
1. 大白话解释
2. 重要性与可信度判断
3. 趋势分析
4. 对普通人的影响
5. 对产品经理的启发
6. 对当前项目的启发
7. 机会判断
8. 风险与噪音
9. 行动建议
10. 一句话结论
