# news-digest/src/aggregator.py
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional
import re
from collections import defaultdict
from difflib import SequenceMatcher
from src.models import NewsItem


class Aggregator:
    """对采集到的新闻进行去重、排序、截取。"""

    AI_KEYWORDS = (
        "ai",
        "artificial intelligence",
        "agi",
        "llm",
        "large language model",
        "gpt",
        "chatgpt",
        "claude",
        "gemini",
        "deepseek",
        "openai",
        "anthropic",
        "machine learning",
        "ml",
        "deep learning",
        "neural",
        "transformer",
        "diffusion",
        "multimodal",
        "rag",
        "agent",
        "copilot",
        "模型",
        "大模型",
        "语言模型",
        "人工智能",
        "机器学习",
        "深度学习",
        "神经网络",
        "多模态",
        "智能体",
        "生成式",
        "算力",
        "推理",
        "训练",
    )

    AI_SOURCES = {
        "Arxiv",
        "OpenAI",
        "Anthropic",
        "Google AI",
        "Reddit r/MachineLearning",
    }

    OFFICIAL_SOURCES = {
        "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "Google AI",
    }

    RELEASE_VERBS = (
        "introducing", "announce", "launch", "release", "available",
        "unveil", "present", "发布", "推出", "上线", "开源", "开放",
    )

    VERSION_PATTERNS = (
        r"\bgpt\s*[-.]?\s*\d+\.?\d*\b",
        r"\bclaude\s*\d+\.?\d*\b",
        r"\bllama\s*\d+\.?\d*\b",
        r"\bgemini\s*\d+\.?\d*\b",
        r"\bdeepseek\s*[-.]?\s*[rR]?\d*\.?\d*\b",
        r"\bmistral\s*\d+\.?\d*\b",
        r"\bqwen\s*\d+\.?\d*\b",
        r"\bv?\d+\.\d+(?:\.\d+)?\b",
        r"\b\d+\.\d+[A-Za-z]*\b",
    )

    def __init__(self, config: dict):
        analysis_config = config.get("analysis", {})
        self.max_per_day = analysis_config.get("max_news_per_day", 10)
        self.require_ai_relevance = analysis_config.get("require_ai_relevance", True)
        self.max_per_source = analysis_config.get("max_news_per_source", 3)
        self.recent_hours = analysis_config.get("recent_hours", 24)
        self.source_weights = {
            "OpenAI": 1.0,
            "Anthropic": 1.0,
            "Google DeepMind": 1.0,
            "Meta AI": 0.95,
            "Google AI": 0.95,
            "VentureBeat AI": 0.9,
            "TechCrunch AI": 0.9,
            "Arxiv": 0.9,
            "Hugging Face": 0.75,
            "Hacker News": 0.8,
            "GitHub Trending": 0.7,
            "Reddit r/MachineLearning": 0.7,
            "机器之心": 0.7,
            "量子位": 0.7,
        }
        self.source_limits = analysis_config.get("source_limits", {})

    def _compute_norms(self, items: List[NewsItem]) -> dict[int, float]:
        """Compute per-source percentile-based score normalization.
        Returns a mapping of item index -> normalized score (0.3-1.0).
        Sources with <3 scored items get a flat 0.6.
        """
        by_source: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for idx, item in enumerate(items):
            if item.score > 0:
                by_source[item.source].append((idx, item.score))

        norms: dict[int, float] = {}
        for source, indexed in by_source.items():
            if len(indexed) < 3:
                for idx, _ in indexed:
                    norms[idx] = 0.6
                continue

            sorted_items = sorted(indexed, key=lambda x: x[1])
            n = len(sorted_items)
            for rank, (idx, _) in enumerate(sorted_items):
                pct = rank / n
                if pct >= 0.95:
                    norms[idx] = 1.0
                elif pct >= 0.80:
                    norms[idx] = 0.8
                elif pct >= 0.50:
                    norms[idx] = 0.5
                else:
                    norms[idx] = 0.3

        return norms

    def _has_version_pattern(self, title: str) -> bool:
        """Return True if title contains a version or model name pattern."""
        title_lower = title.lower()
        return any(re.search(p, title_lower) for p in self.VERSION_PATTERNS)

    def _release_boost(self, item: NewsItem) -> float:
        """Return L1 (+0.15), L2 (+0.10), or 0.0 release signal boost."""
        if item.source not in self.OFFICIAL_SOURCES:
            return 0.0

        title_lower = item.title.lower()
        has_verb = any(v in title_lower for v in self.RELEASE_VERBS)
        if not has_verb:
            return 0.0

        if self._has_version_pattern(item.title):
            return 0.15
        return 0.10

    def _burst_detect(self, items: List[NewsItem]) -> dict[int, float]:
        """Cluster items by title similarity; clusters with >=3 distinct
        sources grant all members +0.10 burst boost."""
        n = len(items)
        clustered: set[int] = set()
        clusters: list[tuple[set[int], set[str]]] = []

        for i in range(n):
            if i in clustered:
                continue
            cluster: set[int] = {i}
            sources: set[str] = {items[i].source}
            for j in range(i + 1, n):
                if j in clustered:
                    continue
                if len(items[i].title) < 10 or len(items[j].title) < 10:
                    continue
                ratio = SequenceMatcher(
                    None, items[i].title.lower(), items[j].title.lower()
                ).ratio()
                if ratio >= 0.5:
                    cluster.add(j)
                    sources.add(items[j].source)
            clustered.update(cluster)
            clusters.append((cluster, sources))

        result: dict[int, float] = {}
        for cluster, sources in clusters:
            if len(sources) >= 3:
                for idx in cluster:
                    result[idx] = 0.10
        return result

    def is_ai_related(self, item: NewsItem) -> bool:
        """Return whether an item is clearly AI-related."""
        if item.source in self.AI_SOURCES:
            return True

        text = " ".join(
            part for part in [item.title, item.summary, item.category, item.source] if part
        ).lower()

        for keyword in self.AI_KEYWORDS:
            keyword = keyword.lower()
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                return True
        return False

    def filter_ai_related(self, items: List[NewsItem]) -> List[NewsItem]:
        """Keep only items that are clearly related to AI."""
        if not self.require_ai_relevance:
            return items
        return [item for item in items if self.is_ai_related(item)]

    def keyword_strength(self, item: NewsItem) -> float:
        """Return a bounded AI keyword signal between 0 and 1."""
        text = " ".join(
            part for part in [item.title, item.summary, item.category, item.source] if part
        ).lower()

        matches = 0
        for keyword in self.AI_KEYWORDS:
            keyword = keyword.lower()
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                matches += 1
        return min(matches / 3, 1.0)

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
        """Pre-compute norms and bursts, then sort by ranking_score."""
        norms = self._compute_norms(items)
        bursts = self._burst_detect(items)
        scored = [
            (self.ranking_score(item, norms, bursts, idx), item)
            for idx, item in enumerate(items)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def ranking_score(
        self,
        item: NewsItem,
        norms: Optional[dict[int, float]] = None,
        bursts: Optional[dict[int, float]] = None,
        item_index: Optional[int] = None,
    ) -> float:
        """Combine source, freshness, normalized score, keyword, release, and burst signals."""
        source_signal = self.source_weights.get(item.source, 0.6)
        age_hours = max(
            (datetime.now(timezone.utc) - item.published).total_seconds() / 3600, 0,
        )
        freshness_signal = max(0.0, 1 - (age_hours / max(self.recent_hours, 1)))

        norm_signal = 0.6
        if norms is not None and item_index is not None:
            norm_signal = norms.get(item_index, 0.6)

        keyword_signal = self.keyword_strength(item)

        release_boost = self._release_boost(item)

        burst_boost = 0.0
        if bursts is not None and item_index is not None:
            burst_boost = bursts.get(item_index, 0.0)

        return (
            source_signal * 0.25
            + freshness_signal * 0.25
            + norm_signal * 0.20
            + keyword_signal * 0.15
            + release_boost
            + burst_boost
        )

    def diversify_sources(self, items: List[NewsItem], limit: Optional[int] = None) -> List[NewsItem]:
        """Limit each source and mix sources so one feed cannot dominate."""
        limit = self.max_per_day if limit is None else limit
        if self.max_per_source <= 0:
            return items[:limit]

        by_source = defaultdict(list)
        for item in items:
            by_source[item.source].append(item)

        source_order = list(by_source)

        selected = []
        selected_by_source = defaultdict(int)
        while len(selected) < limit:
            added = False
            for source in source_order:
                source_limit = self.source_limits.get(source, self.max_per_source)
                if selected_by_source[source] >= source_limit:
                    continue
                queue = by_source[source]
                if not queue:
                    continue

                selected.append(queue.pop(0))
                selected_by_source[source] += 1
                added = True
                if len(selected) >= limit:
                    break

            if not added:
                break

        return selected

    def filter_recent(self, items: List[NewsItem], hours: Optional[int] = None) -> List[NewsItem]:
        """只保留最近 N 小时内的新闻。"""
        hours = self.recent_hours if hours is None else hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [i for i in items if i.published >= cutoff]

    def process(self, items: List[NewsItem], limit: Optional[int] = None) -> List[NewsItem]:
        """完整的处理流水线。"""
        items = self.filter_recent(items)
        items = self.filter_ai_related(items)
        items = self.deduplicate(items)
        items = self.sort_by_score(items)
        return self.diversify_sources(items, limit=limit)

    def split_batches(self, items: List[NewsItem]) -> Tuple[List[NewsItem], List[NewsItem]]:
        """拆分为上午和下午两批。上午最多 10 条，其余为下午。"""
        morning = items[:10]
        afternoon = items[10:] if len(items) > 10 else []
        return morning, afternoon
