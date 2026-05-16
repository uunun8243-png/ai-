from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NewsItem:
    """统一的新闻条目模型，所有采集器输出此格式。"""
    title: str
    url: str
    source: str                # 来源名称，如 "Arxiv", "Hacker News"
    published: datetime
    summary: str               # 原文摘要或正文前 500 字
    content: str = ""          # 原文正文（可选）
    category: str = ""         # 自动分类：大模型/开源/多模态/硬件/行业动态
    score: float = 0.0         # 热度评分，用于排序
    analysis: Optional[dict] = field(default=None)  # 11 维度分析结果
