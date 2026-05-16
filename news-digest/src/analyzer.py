# news-digest/src/analyzer.py
import json
import httpx
from typing import List
from src.models import NewsItem


ANALYSIS_PROMPT = """你是一个 AI 技术导师，用户是 AI 领域的学习者。

请对下面这条新闻进行分析。**根据新闻类型（技术创新/行业趋势/政策法规/产品发布/研究突破/融资动态）调整分析角度，严格按照 JSON 格式输出**：

```json
{{
  "category": "新闻类型：技术创新|行业趋势|政策法规|产品发布|研究突破|融资动态",
  "one_liner": "用一句话说清楚发生了什么（谁+做了什么+关键数据）",
  "background": "背景上下文：为什么会发生、之前行业是什么状态",
  "core_analysis": "核心分析。根据新闻类型输出不同侧重点：\n- 技术创新/研究突破 → 核心技术解读（架构/方法/指标）\n- 行业趋势/融资动态 → 市场影响（规模/玩家/格局变化）\n- 政策法规 → 具体规定和影响范围\n- 产品发布 → 功能亮点和差异化",
  "why_matters": "为什么这条新闻值得关注，对行业/技术/市场有什么影响",
  "learning_value": "作为学习者能从中获得什么：值得关注的技术点、行业认知或新思路",
  "action": "建议行动：收藏|精读原文|动手实践|关注后续|了解即可",
  "trend": "趋势判断：短期热点|中期趋势|长期方向",
  "quick_start": "如果是可上手的技术/工具：如何快速体验（仓库链接/API/命令）。如果是行业资讯/政策则写'无需上手'",
  "insight": "一句话总结，最值得记住的一个点"
}}
```

内容要有实质，不空泛。假设读者有 AI 基础知识，想通过新闻加深技术理解和行业认知。

新闻信息：
标题：{title}
来源：{source}
摘要：{summary}
正文：{content}
"""


class Analyzer:
    """调用 DeepSeek API 对新闻进行 10 维度分析。"""

    def __init__(self, config: dict):
        ds_config = config.get("deepseek", {})
        self.api_key = ds_config.get("api_key", "")
        self.model = ds_config.get("model", "deepseek-chat")
        self.base_url = "https://api.deepseek.com/v1"

    async def analyze(self, item: NewsItem) -> dict:
        """对单条新闻分析，返回 10 维度 JSON。"""
        if not self.api_key:
            return {"error": "DeepSeek API key not configured"}

        prompt = ANALYSIS_PROMPT.format(
            title=item.title,
            source=item.source,
            summary=item.summary,
            content=item.content[:1000] if item.content else "",
        )

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as e:
            print(f"  ⚠ DeepSeek API 分析失败: {e}")
            return {"error": f"分析失败: {str(e)}"}

    async def analyze_batch(self, items: List[NewsItem]) -> List[NewsItem]:
        """批量分析新闻，将分析结果附加到每条新闻。"""
        for item in items:
            analysis = await self.analyze(item)
            item.analysis = analysis
        return items
