# news-digest/src/notifiers/feishu.py
import httpx
from typing import List
from src.models import NewsItem


class FeishuNotifier:
    """通过飞书群机器人 Webhook 推送消息。"""

    def __init__(self, config: dict):
        self.webhook_url = config.get("feishu", {}).get("webhook_url", "")

    def _format_analysis_text(self, item: NewsItem, index: int, total: int) -> str:
        """将单条新闻的 10 维度分析格式化为飞书消息文本。"""
        a = item.analysis or {}
        lines = [
            f"【{index}/{total}】{item.title}",
            f"来源：{item.source}  |  重要程度：{a.get('importance', 'N/A')}",
            "",
        ]

        # 1. 大白话解释
        if a.get("plain_explanation"):
            lines.extend([
                "一、这条新闻在说什么？",
                a["plain_explanation"],
                "",
            ])

        # 2. 重要性
        if a.get("importance_reason"):
            lines.extend([
                "二、为什么值得关注？",
                a["importance_reason"],
                "",
            ])

        # 3. 趋势
        if a.get("trend_name"):
            lines.extend([
                "三、背后趋势",
                f"趋势：{a['trend_name']}（{a.get('trend_duration', '')}）",
                a.get("trend_explanation", ""),
                "",
            ])

        # 4. 对普通人的影响
        if a.get("ordinary_impact"):
            lines.extend([
                "四、普通人怎么看？",
                a["ordinary_impact"],
                f"行动建议：{a.get('ordinary_action', '')}",
                "",
            ])

        # 5. 对 PM 启发
        if a.get("pm_user_need"):
            lines.extend([
                "五、对 AI 产品经理的启发",
                f"用户需求：{a['pm_user_need']}",
                f"产品机会：{a.get('pm_new_product', '')}",
                "",
            ])

        # 6. 行动建议
        action_type = a.get("action_type", "")
        if action_type and action_type != "忽略":
            lines.extend([
                "六、行动建议",
                f"建议：{action_type} — {a.get('action_purpose', '')}",
                f"预计耗时：{a.get('action_time', '')}",
                f"产出：{a.get('action_output', '')}",
                "",
            ])

        # 7. 结论
        if a.get("conclusion"):
            lines.append(f"💡 {a['conclusion']}")

        lines.append("")
        lines.append("—" * 30)
        lines.append("")

        return "\n".join(lines)

    def _format_text_message(self, text: str) -> dict:
        """构造飞书文本消息 JSON。"""
        return {
            "msg_type": "text",
            "content": {
                "text": text,
            },
        }

    async def send_news(self, items: List[NewsItem], batch_label: str = "上午") -> bool:
        """逐条发送新闻分析到飞书群。"""
        if not self.webhook_url:
            print("Feishu webhook URL not configured")
            return False

        total = len(items)
        async with httpx.AsyncClient() as client:
            for i, item in enumerate(items, 1):
                if not item.analysis:
                    continue

                msg_text = self._format_analysis_text(item, i, total)
                header = f"🤖 AI 技术日报 · {batch_label}场\n\n"
                payload = self._format_text_message(header + msg_text)

                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                resp.raise_for_status()

        return True
