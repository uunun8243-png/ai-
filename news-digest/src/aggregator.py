# news-digest/src/aggregator.py
from datetime import datetime, timezone, timedelta
from typing import List, Tuple
from difflib import SequenceMatcher
from src.models import NewsItem


class Aggregator:
    """对采集到的新闻进行去重、排序、截取。"""

    def __init__(self, config: dict):
        analysis_config = config.get("analysis", {})
        self.max_per_day = analysis_config.get("max_news_per_day", 10)

    def deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        """基于标题相似度去重（相似度 > 0.7 视为重复）。"""
        unique = []
        for item in items:
            is_dup = False
            for existing in unique:
                # 短标题不做相似度比较，避免误判
                if len(item.title) < 10 or len(existing.title) < 10:
                    continue
                ratio = SequenceMatcher(None, item.title.lower(), existing.title.lower()).ratio()
                if ratio > 0.7:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(item)
        return unique

    def sort_by_score(self, items: List[NewsItem]) -> List[NewsItem]:
        """按热度评分降序排列。"""
        return sorted(items, key=lambda x: x.score, reverse=True)

    def filter_recent(self, items: List[NewsItem], hours: int = 48) -> List[NewsItem]:
        """只保留最近 N 小时内的新闻。"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [i for i in items if i.published >= cutoff]

    def process(self, items: List[NewsItem]) -> List[NewsItem]:
        """完整的处理流水线。"""
        items = self.filter_recent(items)
        items = self.deduplicate(items)
        items = self.sort_by_score(items)
        return items[:self.max_per_day]

    def split_batches(self, items: List[NewsItem]) -> Tuple[List[NewsItem], List[NewsItem]]:
        """拆分为上午和下午两批。上午最多 10 条，其余为下午。"""
        morning = items[:10]
        afternoon = items[10:] if len(items) > 10 else []
        return morning, afternoon
