import json
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from src.models import NewsItem

FEISHU_BASE = "https://open.feishu.cn/open-apis"


def _card_color(importance: str) -> str:
    """将重要程度映射为飞书卡片颜色。"""
    mapping = {"高": "red", "中": "orange", "低": "blue"}
    return mapping.get(importance, "blue")


def _infer_importance(analysis: dict) -> str:
    """根据 action 字段推断重要程度。"""
    action = analysis.get("action", "")
    if action in ("动手实践", "精读原文"):
        return "高"
    elif action in ("关注后续", "收藏"):
        return "中"
    return "低"


class FeishuNotifier:
    """通过飞书 API 推送消息卡片到群聊。"""

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

    async def _send_card(self, token: str, card: dict):
        """发送一条卡片消息到群聊。"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FEISHU_BASE}/im/v1/messages?receive_id_type=chat_id",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "receive_id": self.chat_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                print(f"  ⚠ 发送飞书消息失败: {data}")

    def _format_analysis_text(self, item: NewsItem, index: int, total: int) -> str:
        """将单条新闻的 10 字段分析格式化为纯文本（备用/调试用）。"""
        a = item.analysis or {}
        lines = [
            f"【{index}/{total}】{item.title}",
            f"{a.get('category', 'N/A')} · {item.source}",
            a.get("one_liner", ""),
            "",
        ]

        if a.get("background"):
            lines.extend(["📖 背景", a["background"], ""])

        if a.get("core_analysis"):
            lines.extend(["🔍 核心分析", a["core_analysis"], ""])

        if a.get("why_matters"):
            lines.extend(["💡 为什么重要", a["why_matters"], ""])

        if a.get("learning_value"):
            lines.extend(["📚 学习价值", a["learning_value"], ""])

        qs = a.get("quick_start", "")
        if qs and qs != "无需上手":
            lines.extend(["🚀 快速上手", qs, ""])

        action = a.get("action", "")
        trend = a.get("trend", "")
        parts = []
        if action:
            parts.append(f"📌 {action}")
        if trend:
            parts.append(f"📈 {trend}")
        if parts:
            lines.append("  ".join(parts))

        if a.get("insight"):
            lines.extend(["", f"💬 {a['insight']}"])

        lines.extend(["", "—" * 30, ""])
        return "\n".join(lines)

    def _build_card(self, item: NewsItem, index: int, total: int) -> dict:
        """将单条新闻的 10 字段分析构建为飞书消息卡片。"""
        a = item.analysis or {}
        importance = _infer_importance(a)
        color = _card_color(importance)

        elements = []

        # 元信息行
        meta_parts = [a.get("category", ""), item.source]
        meta = " · ".join(filter(None, meta_parts))
        if a.get("one_liner"):
            meta += f"\n{a['one_liner']}"
        if meta:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": meta},
            })
            elements.append({"tag": "hr"})

        # 内容区块
        sections = [
            ("📖 背景", a.get("background")),
            ("🔍 核心分析", a.get("core_analysis")),
            ("💡 为什么重要", a.get("why_matters")),
            ("📚 学习价值", a.get("learning_value")),
        ]
        for label, content in sections:
            if content:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**{label}**\n{content}"},
                })

        # 快速上手
        qs = a.get("quick_start", "")
        if qs and qs != "无需上手":
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**🚀 快速上手**\n{qs}"},
            })

        # 底部标签
        footer_parts = []
        if a.get("action"):
            footer_parts.append(f"📌 {a['action']}")
        if a.get("trend"):
            footer_parts.append(f"📈 {a['trend']}")
        footer = "  ·  ".join(footer_parts)
        if footer:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": footer},
            })

        # insight
        if a.get("insight"):
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"💬 {a['insight']}"},
            })

        # 打开原文按钮
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔗 阅读原文"},
                "type": "default",
                "url": item.url,
            }],
        })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"[{importance}] {item.title}"},
                "template": color,
            },
            "elements": elements,
        }

    async def _cleanup_old_messages(self, token: str = "") -> bool:
        """删除 3 天前的机器人消息。"""
        if not self.chat_id:
            return False

        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        cutoff_ts = int(cutoff.timestamp())

        async with httpx.AsyncClient() as client:
            try:
                # 分页查询历史消息
                page_token = None
                while True:
                    params = {
                        "container_id_type": "chat",
                        "container_id": self.chat_id,
                        "page_size": 50,
                        "sort_type": "ByCreateTimeDesc",
                    }
                    if page_token:
                        params["page_token"] = page_token

                    resp = await client.get(
                        f"{FEISHU_BASE}/im/v1/messages",
                        headers={"Authorization": f"Bearer {token}"},
                        params=params,
                        timeout=10.0,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"  ⚠ 查询消息失败: {data}")
                        return False

                    items = data.get("data", {}).get("items", [])
                    for msg in items:
                        sender_type = msg.get("sender", {}).get("sender_type", "")
                        msg_type = msg.get("msg_type", "")
                        if sender_type != "app" or msg_type != "interactive":
                            continue
                        create_time = msg.get("create_time", "0")
                        if create_time and int(create_time) < cutoff_ts:
                            msg_id = msg.get("message_id", "")
                            if msg_id:
                                try:
                                    del_resp = await client.delete(
                                        f"{FEISHU_BASE}/im/v1/messages/{msg_id}",
                                        headers={"Authorization": f"Bearer {token}"},
                                        timeout=10.0,
                                    )
                                    del_data = del_resp.json()
                                    if del_data.get("code") != 0:
                                        print(f"  ⚠ 删除消息 {msg_id} 失败: {del_data}")
                                except Exception as e:
                                    print(f"  ⚠ 删除消息 {msg_id} 异常: {e}")

                    page_token = data.get("data", {}).get("page_token")
                    if not data.get("data", {}).get("has_more"):
                        break
            except Exception as e:
                print(f"  ⚠ 清理旧消息失败: {e}")
                return False

        return True

    async def send_news(self, items: List[NewsItem], batch_label: str = "上午") -> bool:
        """逐条发送新闻卡片到飞书群。"""
        if not self.app_id or not self.app_secret or not self.chat_id:
            print("飞书 API 配置不完整（需要 app_id, app_secret, chat_id）")
            return False

        try:
            token = await self._get_tenant_token()
        except Exception as e:
            print(f"  ✗ 获取飞书 token 失败: {e}")
            return False

        # 清理 3 天前的旧卡片
        await self._cleanup_old_messages(token)

        total = len(items)
        success_count = 0

        for i, item in enumerate(items, 1):
            if not item.analysis:
                continue

            card = self._build_card(item, i, total)
            try:
                await self._send_card(token, card)
                success_count += 1
            except Exception as e:
                print(f"  ⚠ 推送第 {i} 条失败: {e}")

        return success_count > 0

    async def send_alert(self, stage: str, error: str) -> bool:
        """发送失败告警卡片到飞书群。"""
        if not self.app_id or not self.app_secret or not self.chat_id:
            return False

        try:
            token = await self._get_tenant_token()
        except Exception as e:
            print(f"  ✗ 获取飞书 token 失败: {e}")
            return False

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "⚠️ AI 日报推送失败"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**阶段：**{stage}\n**错误：**{error}\n**时间：**{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                    },
                },
            ],
        }

        try:
            await self._send_card(token, card)
            return True
        except Exception as e:
            print(f"  ⚠ 发送告警失败: {e}")
            return False
