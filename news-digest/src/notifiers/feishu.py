import json
import httpx
from typing import List
from src.models import NewsItem

FEISHU_BASE = "https://open.feishu.cn/open-apis"


class FeishuNotifier:
    """通过飞书 API 推送消息到群聊。"""

    def __init__(self, config: dict):
        fc = config.get("feishu", {})
        self.app_id = fc.get("app_id", "")
        self.app_secret = fc.get("app_secret", "")
        self.chat_id = fc.get("chat_id", "")

    async def _get_tenant_token(self) -> str:
        """获取飞书 tenant_access_token。"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"获取飞书 token 失败: {data}")
            return data["tenant_access_token"]

    async def _send_message(self, token: str, text: str):
        """发送一条文本消息到群聊。"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FEISHU_BASE}/im/v1/messages?receive_id_type=chat_id",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "receive_id": self.chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                print(f"  ⚠ 发送飞书消息失败: {data}")

    def _format_analysis_text(self, item: NewsItem, index: int, total: int) -> str:
        """将单条新闻的 10 维度分析格式化为消息文本。"""
        a = item.analysis or {}
        lines = [
            f"【{index}/{total}】{item.title}",
            f"来源：{item.source}  |  重要程度：{a.get('importance', 'N/A')}",
            "",
        ]

        if a.get("plain_explanation"):
            lines.extend(["一、这条新闻在说什么？", a["plain_explanation"], ""])

        if a.get("importance_reason"):
            lines.extend(["二、为什么值得关注？", a["importance_reason"], ""])

        if a.get("trend_name"):
            lines.extend([
                "三、背后趋势",
                f"趋势：{a['trend_name']}（{a.get('trend_duration', '')}）",
                a.get("trend_explanation", ""),
                "",
            ])

        if a.get("ordinary_impact"):
            lines.extend([
                "四、普通人怎么看？",
                a["ordinary_impact"],
                f"行动建议：{a.get('ordinary_action', '')}",
                "",
            ])

        if a.get("pm_user_need"):
            lines.extend([
                "五、对 AI 产品经理的启发",
                f"用户需求：{a['pm_user_need']}",
                f"产品机会：{a.get('pm_new_product', '')}",
                "",
            ])

        action_type = a.get("action_type", "")
        if action_type and action_type != "忽略":
            lines.extend([
                "六、行动建议",
                f"建议：{action_type} — {a.get('action_purpose', '')}",
                f"预计耗时：{a.get('action_time', '')}",
                f"产出：{a.get('action_output', '')}",
                "",
            ])

        if a.get("conclusion"):
            lines.append(f"💡 {a['conclusion']}")

        lines.extend(["", "—" * 30, ""])
        return "\n".join(lines)

    async def send_news(self, items: List[NewsItem], batch_label: str = "上午") -> bool:
        """逐条发送新闻分析到飞书群。"""
        if not self.app_id or not self.app_secret or not self.chat_id:
            print("飞书 API 配置不完整（需要 app_id, app_secret, chat_id）")
            return False

        try:
            token = await self._get_tenant_token()
        except Exception as e:
            print(f"  ✗ 获取飞书 token 失败: {e}")
            return False

        total = len(items)
        success_count = 0

        for i, item in enumerate(items, 1):
            if not item.analysis:
                continue

            msg_text = self._format_analysis_text(item, i, total)
            header = f"🤖 AI 技术日报 · {batch_label}场\n\n"
            try:
                await self._send_message(token, header + msg_text)
                success_count += 1
            except Exception as e:
                print(f"  ⚠ 推送第 {i} 条失败: {e}")

        return success_count > 0
