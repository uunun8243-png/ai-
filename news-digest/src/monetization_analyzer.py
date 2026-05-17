# news-digest/src/monetization_analyzer.py
import json
import os
import httpx
from typing import List
from src.models import NewsItem


MONETIZATION_PROMPT = """你是一个 AI 变现分析师，擅长分析 AI 产品的商业模式和赚钱逻辑。

请分析下面这个 AI 变现项目，严格按照 JSON 格式输出：

```json
{{
  "one_liner": "一句话概括这个项目是做什么的",
  "business_model": "商业模式：SaaS|订阅|一次性买断|广告|交易抽成|开源+托管|混合",
  "revenue_estimate": "收入估算（基于公开数据，如'月收入 $5K-10K'，不确定则写'暂无公开数据'）",
  "target_users": "目标用户群体",
  "tech_stack": "用到的 AI 技术/模型/框架",
  "why_it_works": "为什么能赚钱——核心洞察（解决了什么痛点、有什么壁垒）",
  "china_adaptation": "国内借鉴建议（类似模式能否复制、需要怎么调整）",
  "action": "行动建议（如果想学习/复刻，第一步做什么）"
}}
```

内容要具体、有实质，不空泛。基于项目实际信息分析，不要编造数据。

项目信息：
标题：{title}
来源：{source}
简介：{summary}
"""


class MonetizationAnalyzer:
    """调用 DeepSeek API 对变现项目进行商业模式分析。"""

    def __init__(self, config: dict):
        ds_config = config.get("deepseek", {})
        self.api_key = ds_config.get("api_key", "")
        self.model = ds_config.get("model", "deepseek-chat")
        self.base_url = "https://api.deepseek.com/v1"

    async def analyze(self, item: NewsItem) -> dict:
        if not self.api_key:
            return {"error": "DeepSeek API key not configured"}

        prompt = MONETIZATION_PROMPT.format(
            title=item.title,
            source=item.source,
            summary=item.summary[:1000],
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
                content = content.strip()
                if content.startswith("```"):
                    content = content.strip("`")
                    content = content.removeprefix("json").removeprefix("JSON").strip()
                return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"  ⚠ 变现分析 JSON 解析失败: {e}")
            return {"error": f"分析失败: JSON 解析错误"}
        except Exception as e:
            print(f"  ⚠ 变现分析失败: {e}")
            return {"error": f"分析失败: {str(e)}"}

    async def analyze_batch(self, items: List[NewsItem]) -> List[NewsItem]:
        for item in items:
            analysis = await self.analyze(item)
            item.analysis = analysis
        return items
