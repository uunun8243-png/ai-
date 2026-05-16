# Batch Size Increase & Scoring Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase per-batch news to 15, add 5 new RSS collectors (14 total sources), and redesign scoring with per-source normalization, official release boost, and cross-source burst detection.

**Architecture:** Extend the existing Aggregator with three new scoring signals while keeping the pipeline structure unchanged. Add 5 new collector files following the existing `BaseCollector` pattern. All new scoring logic lives in `aggregator.py`; collectors are independent RSS feed readers.

**Tech Stack:** Python 3.x, httpx, feedparser, pyyaml, pytest, pytest-asyncio

---

### Task 1: Config changes

**Files:**
- Modify: `news-digest/config.yaml`

- [ ] **Step 1: Update config.yaml**

```yaml
feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"
  chat_id: "${FEISHU_CHAT_ID}"

deepseek:
  api_key: "${DEEPSEEK_API_KEY}"
  model: "deepseek-v4-flash"

sources:
  arxiv: true
  github_trending: true
  hackernews: true
  blogs: true
  reddit_ml: true
  zh_sources: true
  meta_ai: true
  huggingface: true
  deepmind: true
  venturebeat: true
  techcrunch: true

schedule:
  time: "08:00"
  timezone: "Asia/Shanghai"

analysis:
  max_news_per_day: 15
  candidate_pool_size: 45
  max_news_per_source: 3
  recent_hours: 24
  sent_state_path: ".digest-state/sent_items.json"
  output_language: "zh-CN"
  require_ai_relevance: true
  source_limits:
    OpenAI: 2
    Anthropic: 2
    Google DeepMind: 2
    Meta AI: 2
    Hugging Face: 2
    Google AI: 2
    Arxiv: 3
    GitHub Trending: 3
    Hacker News: 2
    Reddit r/MachineLearning: 2
    VentureBeat AI: 4
    TechCrunch AI: 4
    机器之心: 2
    量子位: 2
```

- [ ] **Step 2: Commit**

```bash
git add news-digest/config.yaml
git commit -m "feat: increase batch size to 15, add 5 new source flags and per-source limits"
```

---

### Task 2: Aggregator — per-source normalization

**Files:**
- Modify: `news-digest/src/aggregator.py`
- Test: `news-digest/tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

Add to `news-digest/tests/test_aggregator.py`:

```python
def test_per_source_norm_top_item_gets_1_0():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    items = [
        make_ai_item("Top HN post", "Hacker News", score=500),
        make_ai_item("Mid HN post", "Hacker News", score=200),
        make_ai_item("Mid2 HN post", "Hacker News", score=150),
        make_ai_item("Low HN post", "Hacker News", score=50),
    ]
    norms = agg._compute_norms(items)
    assert norms[0] == 1.0  # Top 5%: 500 is top


def test_per_source_norm_small_source_defaults_to_0_6():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    items = [
        make_ai_item("Only post", "OpenAI", score=10),
        make_ai_item("Another", "OpenAI", score=20),
    ]
    norms = agg._compute_norms(items)
    assert norms[0] == 0.6
    assert norms[1] == 0.6


def test_per_source_norm_cross_source_independent():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    items = [
        make_ai_item("Big GitHub repo", "GitHub Trending", score=50000),
        make_ai_item("Small GitHub repo", "GitHub Trending", score=10),
        make_ai_item("Big GitHub repo 2", "GitHub Trending", score=400),
        make_ai_item("Big HN post", "Hacker News", score=500),
        make_ai_item("Small HN post", "Hacker News", score=10),
        make_ai_item("Small HN post 2", "Hacker News", score=15),
    ]
    norms = agg._compute_norms(items)
    # GitHub: 50000 is top, 400 is mid, 10 is bottom
    assert norms[0] == 1.0  # 50000
    assert norms[2] == 0.8  # 400 (top 20%)
    # HN: 500 is top, 15 is mid, 10 is bottom
    assert norms[3] == 1.0  # 500
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py::test_per_source_norm_top_item_gets_1_0 tests/test_aggregator.py::test_per_source_norm_small_source_defaults_to_0_6 tests/test_aggregator.py::test_per_source_norm_cross_source_independent -v
```

Expected: AttributeError, `_compute_norms` does not exist.

- [ ] **Step 3: Implement `_compute_norms`**

In `news-digest/src/aggregator.py`, add to the Aggregator class after `__init__`:

```python
def _compute_norms(self, items: List[NewsItem]) -> dict[int, float]:
    """Compute per-source percentile-based score normalization.

    Returns a mapping of item index → normalized score (0.3–1.0).
    Sources with <3 scored items get a flat 0.6 to avoid unreliable
    percentile calculation from small samples.
    """
    from collections import defaultdict

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
```

Items without a score (score=0) are omitted from `_compute_norms` — they'll be handled in `ranking_score` with a default of 0.6.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py::test_per_source_norm_top_item_gets_1_0 tests/test_aggregator.py::test_per_source_norm_small_source_defaults_to_0_6 tests/test_aggregator.py::test_per_source_norm_cross_source_independent -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add news-digest/src/aggregator.py news-digest/tests/test_aggregator.py
git commit -m "feat: add per-source percentile score normalization"
```

---

### Task 3: Aggregator — official release signal

**Files:**
- Modify: `news-digest/src/aggregator.py`
- Test: `news-digest/tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

Add to `news-digest/tests/test_aggregator.py`:

```python
def test_release_boost_l1_version_release():
    agg = Aggregator({"analysis": {}})
    item = make_ai_item("Introducing GPT-5: next-generation language model", "OpenAI", score=0)
    assert agg._release_boost(item) == 0.15


def test_release_boost_l2_feature_release():
    agg = Aggregator({"analysis": {}})
    item = make_ai_item("Anthropic launches Artifacts for Claude", "Anthropic", score=0)
    assert agg._release_boost(item) == 0.10


def test_release_boost_no_verb_no_boost():
    agg = Aggregator({"analysis": {}})
    item = make_ai_item("Our approach to frontier model safety", "OpenAI", score=0)
    assert agg._release_boost(item) == 0.0


def test_release_boost_third_party_no_boost():
    agg = Aggregator({"analysis": {}})
    item = make_ai_item("OpenAI launches GPT-5 today", "VentureBeat AI", score=0)
    assert agg._release_boost(item) == 0.0


def test_release_boost_chinese_release_verb():
    agg = Aggregator({"analysis": {}})
    item = make_ai_item("Meta 发布 Llama 4 开源大模型", "Meta AI", score=0)
    assert agg._release_boost(item) == 0.15
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py -k "release_boost" -v
```

Expected: AttributeError, `_release_boost` does not exist.

- [ ] **Step 3: Implement `_release_boost` and `_has_version_pattern`**

In `news-digest/src/aggregator.py`, add class-level constants and methods:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py -k "release_boost" -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add news-digest/src/aggregator.py news-digest/tests/test_aggregator.py
git commit -m "feat: add official release signal boost (L1/L2)"
```

---

### Task 4: Aggregator — cross-source burst detection

**Files:**
- Modify: `news-digest/src/aggregator.py`
- Test: `news-digest/tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

Add to `news-digest/tests/test_aggregator.py`:

```python
def test_burst_detect_three_sources_boosts():
    agg = Aggregator({"analysis": {}})
    items = [
        make_ai_item("GPT-5 announced by OpenAI", "OpenAI", score=0),
        make_ai_item("GPT-5 launch: what you need to know", "VentureBeat AI", score=0),
        make_ai_item("OpenAI releases GPT-5 model", "TechCrunch AI", score=0),
        make_ai_item("Some unrelated Arxiv paper", "Arxiv", score=0),
    ]
    boosts = agg._burst_detect(items)
    assert boosts.get(0) == 0.10
    assert boosts.get(1) == 0.10
    assert boosts.get(2) == 0.10
    assert 3 not in boosts  # unrelated


def test_burst_detect_only_two_sources_no_boost():
    agg = Aggregator({"analysis": {}})
    items = [
        make_ai_item("Claude 4 announced", "Anthropic", score=0),
        make_ai_item("Anthropic releases Claude 4", "VentureBeat AI", score=0),
    ]
    boosts = agg._burst_detect(items)
    assert boosts == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py -k "burst_detect" -v
```

Expected: AttributeError, `_burst_detect` does not exist.

- [ ] **Step 3: Implement `_burst_detect`**

In `news-digest/src/aggregator.py`, add method:

```python
def _burst_detect(self, items: List[NewsItem]) -> dict[int, float]:
    """Cluster items by title similarity; clusters with ≥3 distinct
    sources grant all members +0.10 burst boost.

    Returns mapping of item index → boost value.
    """
    from difflib import SequenceMatcher

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py -k "burst_detect" -v
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add news-digest/src/aggregator.py news-digest/tests/test_aggregator.py
git commit -m "feat: add cross-source burst detection for major news events"
```

---

### Task 5: Aggregator — updated ranking_score

**Files:**
- Modify: `news-digest/src/aggregator.py`
- Test: `news-digest/tests/test_aggregator.py`

- [ ] **Step 1: Update `test_ranking_score_normalizes_raw_source_scores`**

Replace the existing test with one that tests the new formula:

```python
def test_ranking_score_prefers_official_release_with_burst():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    now = datetime.now(timezone.utc)

    # Simulate GPT-5 launch: OpenAI official + covered by 2+ other sources
    openai_item = make_ai_item("Introducing GPT-5", "OpenAI", score=0)
    openai_item.published = now - timedelta(hours=1)

    hn_item = make_ai_item("Show HN: my AI agent side project", "Hacker News", score=300)
    hn_item.published = now - timedelta(hours=1)

    # With per-source norm, release boost, and burst: OpenAI should win
    items = [openai_item, hn_item]
    norms = agg._compute_norms(items)
    boosts = agg._burst_detect(items)
    # GPT-5 release: source=1.0, fresh=0.96, norm=0.6 (no score), kw=0.33, release=0.15, burst=0
    # HN: source=0.8, fresh=0.96, norm=1.0, kw=0.33, release=0, burst=0
    score_o = agg.ranking_score(openai_item, norms, boosts)
    score_h = agg.ranking_score(hn_item, norms, boosts)
    assert score_o > score_h
```

- [ ] **Step 2: Update `source_weights` in `__init__`**

Replace the existing `self.source_weights` block in `__init__`:

```python
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
```

- [ ] **Step 3: Update `ranking_score` signature and formula**

Replace the existing `ranking_score` method:

```python
def ranking_score(
    self,
    item: NewsItem,
    norms: dict[int, float] | None = None,
    bursts: dict[int, float] | None = None,
    item_index: int | None = None,
) -> float:
    """Combine source, freshness, per-source normalized popularity,
    keyword signal, release boost, and burst signal.

    Pass item_index (position in the current candidate list) so the
    method can look up pre-computed norms and bursts.
    """
    source_signal = self.source_weights.get(item.source, 0.6)
    age_hours = max(
        (datetime.now(timezone.utc) - item.published).total_seconds() / 3600,
        0,
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
```

- [ ] **Step 4: Update `sort_by_score` to compute norms and bursts once**

```python
def sort_by_score(self, items: List[NewsItem]) -> List[NewsItem]:
    """Sort by ranking score descending. Pre-computes per-source norms
    and burst signals once for the entire candidate set."""
    norms = self._compute_norms(items)
    bursts = self._burst_detect(items)
    scored = [
        (self.ranking_score(item, norms, bursts, idx), item)
        for idx, item in enumerate(items)
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]
```

- [ ] **Step 5: Run all aggregator tests**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py -v
```

Expected: All tests pass (existing ones may need minor adjustment for new weights).

- [ ] **Step 6: Commit**

```bash
git add news-digest/src/aggregator.py news-digest/tests/test_aggregator.py
git commit -m "feat: redesigned ranking score with per-source norm, release boost, burst"
```

---

### Task 6: Aggregator — source_limits in diversify_sources

**Files:**
- Modify: `news-digest/src/aggregator.py`
- Test: `news-digest/tests/test_aggregator.py`

- [ ] **Step 1: Update `__init__` to load source_limits**

Add after `self.source_weights` in `__init__`:

```python
self.source_limits = analysis_config.get("source_limits", {})
```

- [ ] **Step 2: Update `diversify_sources` to use per-source limits**

Replace existing `diversify_sources`:

```python
def diversify_sources(self, items: List[NewsItem], limit: int | None = None) -> List[NewsItem]:
    """Limit each source per configured source_limits (falling back to
    max_news_per_source) and mix sources via round-robin so one feed
    cannot dominate."""
    limit = self.max_per_day if limit is None else limit

    by_source: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        by_source[item.source].append(item)

    source_order = list(by_source)
    selected: list[NewsItem] = []
    selected_by_source: dict[str, int] = defaultdict(int)

    while len(selected) < limit:
        added = False
        for source in source_order:
            source_limit = self.source_limits.get(
                source, self.max_per_source
            )
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
```

- [ ] **Step 3: Add test for source_limits from config**

```python
def test_diversify_sources_uses_config_source_limits():
    agg = Aggregator({"analysis": {
        "max_news_per_day": 6,
        "max_news_per_source": 3,
        "source_limits": {
            "VentureBeat AI": 2,
            "Arxiv": 1,
        }
    }})
    items = [
        make_ai_item("VB news 1", "VentureBeat AI", score=100),
        make_ai_item("VB news 2", "VentureBeat AI", score=99),
        make_ai_item("VB news 3", "VentureBeat AI", score=98),
        make_ai_item("Arxiv paper 1", "Arxiv", score=100),
        make_ai_item("Arxiv paper 2", "Arxiv", score=99),
        make_ai_item("HN post 1", "Hacker News", score=100),
    ]
    result = agg.diversify_sources(items)
    # VentureBeat max 2, Arxiv max 1, HN falls back to default 3
    vb_count = sum(1 for i in result if i.source == "VentureBeat AI")
    arxiv_count = sum(1 for i in result if i.source == "Arxiv")
    assert vb_count == 2
    assert arxiv_count == 1
```

- [ ] **Step 4: Run tests**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py -k "diversify" -v
```

Expected: 3 PASS (2 existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add news-digest/src/aggregator.py news-digest/tests/test_aggregator.py
git commit -m "feat: support per-source output limits via config source_limits"
```

---

### Task 7: Meta AI collector

**Files:**
- Create: `news-digest/src/collectors/meta_ai_collector.py`

- [ ] **Step 1: Write collector**

```python
import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class MetaAICollector(BaseCollector):
    source_key = "meta_ai"
    source_name = "Meta AI"

    FEED_URL = "https://ai.meta.com/blog/feed/"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        feed = feedparser.parse(self.FEED_URL)
        items = []
        for entry in feed.entries[:5]:
            published = datetime.now(timezone.utc)
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            items.append(NewsItem(
                title=entry.title,
                url=entry.link,
                source=self.source_name,
                published=published,
                summary=entry.get("summary", "")[:500],
                category="行业动态",
            ))

        return items
```

- [ ] **Step 2: Commit**

```bash
git add news-digest/src/collectors/meta_ai_collector.py
git commit -m "feat: add Meta AI blog collector"
```

---

### Task 8: Hugging Face collector

**Files:**
- Create: `news-digest/src/collectors/huggingface_collector.py`

- [ ] **Step 1: Write collector**

```python
import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class HuggingFaceCollector(BaseCollector):
    source_key = "huggingface"
    source_name = "Hugging Face"

    FEED_URL = "https://huggingface.co/blog/feed.xml"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        feed = feedparser.parse(self.FEED_URL)
        items = []
        for entry in feed.entries[:5]:
            published = datetime.now(timezone.utc)
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            items.append(NewsItem(
                title=entry.title,
                url=entry.link,
                source=self.source_name,
                published=published,
                summary=entry.get("summary", "")[:500],
                category="开源项目",
            ))

        return items
```

- [ ] **Step 2: Commit**

```bash
git add news-digest/src/collectors/huggingface_collector.py
git commit -m "feat: add Hugging Face blog collector"
```

---

### Task 9: Google DeepMind collector

**Files:**
- Create: `news-digest/src/collectors/deepmind_collector.py`

- [ ] **Step 1: Write collector**

```python
import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class DeepMindCollector(BaseCollector):
    source_key = "deepmind"
    source_name = "Google DeepMind"

    FEED_URL = "https://deepmind.google/blog/feed.xml"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        feed = feedparser.parse(self.FEED_URL)
        items = []
        for entry in feed.entries[:5]:
            published = datetime.now(timezone.utc)
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            items.append(NewsItem(
                title=entry.title,
                url=entry.link,
                source=self.source_name,
                published=published,
                summary=entry.get("summary", "")[:500],
                category="行业动态",
            ))

        return items
```

- [ ] **Step 2: Commit**

```bash
git add news-digest/src/collectors/deepmind_collector.py
git commit -m "feat: add Google DeepMind blog collector"
```

---

### Task 10: VentureBeat AI collector

**Files:**
- Create: `news-digest/src/collectors/venturebeat_collector.py`

- [ ] **Step 1: Write collector**

```python
import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class VentureBeatCollector(BaseCollector):
    source_key = "venturebeat"
    source_name = "VentureBeat AI"

    FEED_URL = "https://venturebeat.com/category/ai/feed/"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        feed = feedparser.parse(self.FEED_URL)
        items = []
        for entry in feed.entries[:10]:
            published = datetime.now(timezone.utc)
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            items.append(NewsItem(
                title=entry.title,
                url=entry.link,
                source=self.source_name,
                published=published,
                summary=entry.get("summary", "")[:500],
                category="行业动态",
            ))

        return items
```

- [ ] **Step 2: Commit**

```bash
git add news-digest/src/collectors/venturebeat_collector.py
git commit -m "feat: add VentureBeat AI collector"
```

---

### Task 11: TechCrunch AI collector

**Files:**
- Create: `news-digest/src/collectors/techcrunch_collector.py`

- [ ] **Step 1: Write collector**

```python
import feedparser
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class TechCrunchCollector(BaseCollector):
    source_key = "techcrunch"
    source_name = "TechCrunch AI"

    FEED_URL = "https://techcrunch.com/category/artificial-intelligence/feed/"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        feed = feedparser.parse(self.FEED_URL)
        items = []
        for entry in feed.entries[:10]:
            published = datetime.now(timezone.utc)
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            items.append(NewsItem(
                title=entry.title,
                url=entry.link,
                source=self.source_name,
                published=published,
                summary=entry.get("summary", "")[:500],
                category="行业动态",
            ))

        return items
```

- [ ] **Step 2: Commit**

```bash
git add news-digest/src/collectors/techcrunch_collector.py
git commit -m "feat: add TechCrunch AI collector"
```

---

### Task 12: Main.py — register new collectors

**Files:**
- Modify: `news-digest/src/main.py`

- [ ] **Step 1: Add imports for new collectors**

In `news-digest/src/main.py`, add imports after the existing collector imports (after line 15):

```python
from src.collectors.meta_ai_collector import MetaAICollector
from src.collectors.huggingface_collector import HuggingFaceCollector
from src.collectors.deepmind_collector import DeepMindCollector
from src.collectors.venturebeat_collector import VentureBeatCollector
from src.collectors.techcrunch_collector import TechCrunchCollector
```

- [ ] **Step 2: Add new collectors to `get_collectors`**

Replace the existing `get_collectors` function:

```python
def get_collectors(config: dict) -> list:
    """实例化所有采集器。"""
    return [
        ArxivCollector(config),
        GitHubTrendingCollector(config),
        HackerNewsCollector(config),
        BlogsCollector(config),
        RedditCollector(config),
        ZhSourcesCollector(config),
        MetaAICollector(config),
        HuggingFaceCollector(config),
        DeepMindCollector(config),
        VentureBeatCollector(config),
        TechCrunchCollector(config),
    ]
```

- [ ] **Step 3: Commit**

```bash
git add news-digest/src/main.py
git commit -m "feat: register 5 new collectors in main pipeline"
```

---

### Task 13: Update existing tests for new params

**Files:**
- Modify: `news-digest/tests/test_aggregator.py`

The old `test_ranking_score_normalizes_raw_source_scores` used the old formula which is now invalid. We already replaced it in Task 5. Now check for other tests that may break.

- [ ] **Step 1: Update `test_sort_by_score`**

The test_sort_by_score uses scores 10, 100, 50 with source "Test". With the new formula, all items share the same source so norm scores are identical. Items without published dates default to now (=fresh). The order should still be by score since source/freshness/keyword are identical:

```python
def test_sort_by_score():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    now = datetime.now(timezone.utc)
    a = make_item("A", score=10)
    b = make_item("B", score=100)
    c = make_item("C", score=50)
    a.published = now
    b.published = now
    c.published = now
    items = [a, b, c]
    result = agg.sort_by_score(items)
    assert [i.title for i in result] == ["B", "C", "A"]
```

(This test already passes since norms are consistent within a single source and sort within equal norms falls back to original order... actually, norms give same source different scores. Let me think: 3 items all from "Test" with scores 10, 50, 100. n=3, rank 0→ pct=0 → 0.3, rank 1→ pct=0.33 → 0.5, rank 2→ pct=0.67 → 0.5. So norm(100)=0.5, norm(50)=0.5, norm(10)=0.3. Score formula gives highest score to B (100), then C (50), then A (10). Order: B, C, A. ✓)

- [ ] **Step 2: Run full test suite**

```bash
cd news-digest && python -m pytest tests/test_aggregator.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit (if any changes needed)**

```bash
git add news-digest/tests/test_aggregator.py
git commit -m "test: fix existing tests for new scoring formula"
```

---

### Task 14: README update

**Files:**
- Modify: `news-digest/README.md`

- [ ] **Step 1: Update source count and add new features**

Replace the 功能 section description for sources:

Line 7: `- 自动采集 9 个数据源：Arxiv、GitHub Trending、Hacker News、OpenAI/Anthropic/Google AI Blog、Reddit、机器之心、量子位`

Change to:

```
- 自动采集 14 个数据源：OpenAI/Anthropic/Google DeepMind/Meta AI/Google AI Blog、Arxiv、Hugging Face、Hacker News、GitHub Trending、VentureBeat AI、TechCrunch AI、Reddit、机器之心、量子位
```

Add "15条/批" description on line 12:

```
- 飞书群机器人推送，上午/下午各 15 条
```

Update the config table `max_news_per_day` default from `10` to `15`, `candidate_pool_size` from `30` to `45`.

- [ ] **Step 2: Commit**

```bash
git add news-digest/README.md
git commit -m "docs: update README for 14 sources, 15/batch, new scoring features"
```

---

### Task 15: Integration smoke test

**Files:**
- (no files — run test)

- [ ] **Step 1: Run the full test suite**

```bash
cd news-digest && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify import chain**

```bash
cd news-digest && python -c "from src.aggregator import Aggregator; from src.collectors.meta_ai_collector import MetaAICollector; from src.collectors.huggingface_collector import HuggingFaceCollector; from src.collectors.deepmind_collector import DeepMindCollector; from src.collectors.venturebeat_collector import VentureBeatCollector; from src.collectors.techcrunch_collector import TechCrunchCollector; print('All imports OK')"
```

Expected: `All imports OK`

- [ ] **Step 3: Commit final check**

```bash
git status
```

Verify all changes are committed and working tree is clean.
