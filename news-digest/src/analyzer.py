# news-digest/src/analyzer.py
import json
import httpx
from typing import List
from src.models import NewsItem


ANALYSIS_PROMPT = """你是一个 AI 前沿新闻拆解助手。

请对下面这条新闻进行深度分析，**严格按照 JSON 格式**输出，不要输出其他内容：

```json
{{
  "plain_explanation": "用3-5句大白话解释：谁做了什么，和普通人有什么关系",
  "importance": "高|中|低",
  "scope": "普通用户|开发者|AI产品经理|企业|创业者",
  "credibility": "强|中|弱",
  "trend_forming": "是|否|观察中",
  "importance_reason": "为什么这条新闻值得关注",
  "trend_name": "趋势名称",
  "trend_explanation": "大白话解释趋势",
  "trend_evidence": "为什么这条新闻能代表这个趋势",
  "trend_duration": "短期热点|中期趋势|长期方向",
  "ordinary_impact": "这条新闻和我有什么关系",
  "ordinary_action": "我需要马上学习或使用吗",
  "ordinary_affect": "它会影响我的学习、工作或信息获取方式吗",
  "ordinary_focus": "我应该关注什么，不需要焦虑什么",
  "pm_user_need": "它说明了什么用户需求",
  "pm_pain_point": "它解决了什么痛点",
  "pm_design_takeaway": "它的产品设计有什么值得学",
  "pm_new_product": "它可能启发什么新产品",
  "pm_portfolio": "有没有可以放进作品集的方向",
  "noise_marketing": "这条新闻有没有营销成分",
  "noise_exaggeration": "有没有被媒体夸大的地方",
  "noise_unreliable": "哪些结论不能直接相信",
  "noise_misunderstanding": "普通人最容易误解什么",
  "action_type": "收藏|学习|试用|拆解|做demo|忽略",
  "action_purpose": "行动目的",
  "action_time": "预计耗时",
  "action_output": "预期产出",
  "conclusion": "一句话总结真正值得记住的点"
}}
```

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

    async def analyze_batch(self, items: List[NewsItem]) -> List[NewsItem]:
        """批量分析新闻，将分析结果附加到每条新闻。"""
        for item in items:
            analysis = await self.analyze(item)
            item.analysis = analysis
        return items
