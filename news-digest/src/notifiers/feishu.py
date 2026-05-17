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

    @staticmethod
    def _sort_by_priority(items: List[NewsItem]) -> List[NewsItem]:
        """按优先级排序：高 → 中 → 低，同级保持原顺序。"""
        order = {"高": 0, "中": 1, "低": 2}
        return sorted(items, key=lambda x: order.get(_infer_importance(x.analysis or {}), 3))

    def _build_priority_card(self, items: List[NewsItem], batch_label: str, token_summary: str = "") -> dict:
        """将多条新闻构建为一张按优先级分区的飞书消息卡片。

        卡片结构：
          🔴/🟡/🔵 高/中/低 — 每个分区包含文章的完整分析
          标题行格式：{badge} [{action}] {title} — {one_liner}
          每个条目含背景/核心分析/为什么重要/学习价值/应用实例等字段
        """
        valid = [it for it in items if it.analysis]
        sorted_items = self._sort_by_priority(valid)

        groups = {"高": [], "中": [], "低": []}
        for it in sorted_items:
            importance = _infer_importance(it.analysis or {})
            groups[importance].append(it)

        elements = []

        # ── 空状态处理 ──
        if not sorted_items:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "本次暂无新闻"},
            })
            return {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": f"📋 AI 日报 · {batch_label}"},
                    "template": "blue",
                },
                "elements": elements,
            }

        # ── 优先级分区 ──
        imp_labels = [("🔴 高", "高"), ("🟡 中", "中"), ("🔵 低", "低")]
        for section_header, key in imp_labels:
            group_items = groups[key]
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{section_header}（{len(group_items)} 条）**"},
            })

            if not group_items:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "暂无此优先级的新闻"},
                })
                continue

            for idx, it in enumerate(group_items):
                a = it.analysis or {}
                badge = {"高": "🔴", "中": "🟡", "低": "🔵"}.get(key, "⚪")
                action_label = a.get("action", "")
                one_liner = a.get("one_liner", "")
                title_line = f"{badge} **[{action_label}]** {it.title}"
                if one_liner:
                    title_line += f" — {one_liner}"
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"{title_line}\n{a.get('category', '')} · {it.source}"},
                })

                sections = [
                    ("📖 背景", a.get("background")),
                    ("🔍 核心分析", a.get("core_analysis")),
                    ("💡 为什么重要", a.get("why_matters")),
                    ("📚 学习价值", a.get("learning_value")),
                    ("💡 应用实例", a.get("application_example")),
                ]
                has_content = any(c for _, c in sections)
                if has_content:
                    for label, content in sections:
                        if content:
                            elements.append({
                                "tag": "div",
                                "text": {"tag": "lark_md", "content": f"**{label}**\n{content}"},
                            })

                qs = a.get("quick_start", "")
                if qs and qs != "无需上手":
                    elements.append({
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"**🚀 快速上手**\n{qs}"},
                    })

                footer_parts = []
                if a.get("action"):
                    footer_parts.append(f"📌 {a['action']}")
                if a.get("trend"):
                    footer_parts.append(f"📈 {a['trend']}")
                if footer_parts:
                    elements.append({"tag": "hr"})
                    elements.append({
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": "  ·  ".join(footer_parts)},
                    })

                if a.get("insight"):
                    elements.append({
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"💬 {a['insight']}"},
                    })

                elements.append({
                    "tag": "action",
                    "actions": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔗 阅读原文"},
                        "type": "default",
                        "url": it.url,
                    }],
                })

                if idx < len(group_items) - 1:
                    elements.append({"tag": "hr"})

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📋 AI 日报 · {batch_label}"},
                "template": "blue",
            },
            "elements": elements,
        }
        if token_summary:
            card["elements"].append({"tag": "hr"})
            card["elements"].append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"⚡ Token: {token_summary}"},
            })
        return card

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

    async def send_news(self, items: List[NewsItem], batch_label: str = "上午", token_summary: str = "") -> bool:
        """将一批新闻以 Tab 卡片形式发送到飞书群（只发 1 条消息）。"""
        if not self.app_id or not self.app_secret or not self.chat_id:
            print("飞书 API 配置不完整（需要 app_id, app_secret, chat_id）")
            return False

        try:
            token = await self._get_tenant_token()
        except Exception as e:
            print(f"  ✗ 获取飞书 token 失败: {e}")
            return False

        # 清理 3 天前的旧卡片
        try:
            await self._cleanup_old_messages(token)
        except Exception as e:
            print(f"  ⚠ 清理旧消息失败: {e}")

        # 构建优先级分区卡片并发送
        try:
            card = self._build_priority_card(items, batch_label, token_summary)
            await self._send_card(token, card)
            return True
        except Exception as e:
            print(f"  ✗ 发送卡片失败: {e}")
            return False

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

    def _build_monetization_card(self, items: List[NewsItem], batch_label: str) -> dict:
        """构建变现项目的独立飞书卡片。"""
        elements = []

        for idx, it in enumerate(items):
            a = it.analysis or {}
            if not a or "error" in a:
                continue

            title_line = f"**🔥 项目 {idx + 1}：{it.title}**"
            one_liner = a.get("one_liner", "")
            if one_liner:
                title_line += f"\n💡 {one_liner}"

            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": title_line},
            })

            meta_lines = []
            if a.get("business_model"):
                meta_lines.append(f"💳 **商业模式**：{a['business_model']}")
            if a.get("revenue_estimate"):
                meta_lines.append(f"💰 **收入估算**：{a['revenue_estimate']}")
            if a.get("target_users"):
                meta_lines.append(f"👥 **目标用户**：{a['target_users']}")
            if a.get("tech_stack"):
                meta_lines.append(f"⚙️ **技术栈**：{a['tech_stack']}")
            if meta_lines:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "\n".join(meta_lines)},
                })

            if a.get("why_it_works"):
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**为什么能赚钱**\n{a['why_it_works']}"},
                })
            if a.get("china_adaptation"):
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**国内借鉴**\n{a['china_adaptation']}"},
                })
            if a.get("action"):
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"📌 **{a['action']}**"},
                })

            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🔗 查看原文"},
                    "type": "default",
                    "url": it.url,
                }],
            })

        if not elements:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "本次暂无变现项目"},
            })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"💰 AI 变现项目 · {batch_label}"},
                "template": "yellow",
            },
            "elements": elements,
        }

    async def send_monetization(self, items: List[NewsItem], batch_label: str = "上午") -> bool:
        """发送变现项目独立卡片到飞书群。"""
        if not self.app_id or not self.app_secret or not self.chat_id:
            print("飞书 API 配置不完整")
            return False
        if not items:
            print("无变现项目可推送")
            return False

        try:
            token = await self._get_tenant_token()
        except Exception as e:
            print(f"  ✗ 获取飞书 token 失败: {e}")
            return False

        try:
            card = self._build_monetization_card(items, batch_label)
            await self._send_card(token, card)
            return True
        except Exception as e:
            print(f"  ✗ 发送变现卡片失败: {e}")
            return False
