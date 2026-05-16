# Batch Size Increase & Scoring Redesign

## Summary

Increase per-batch news from 10 to 15, add 5 new data sources (14 total), and redesign the scoring mechanism with per-source normalization, official release signal boosting, and cross-source burst detection.

## Data Sources

### New Collectors (5)

| Collector | Source | Method | Limit |
|-----------|--------|--------|:-----:|
| `meta_ai_collector.py` | Meta AI Blog | RSS: `ai.meta.com/blog/feed/` | 5 |
| `huggingface_collector.py` | Hugging Face Blog | RSS: `huggingface.co/blog/feed.xml` | 5 |
| `deepmind_collector.py` | Google DeepMind | RSS: `deepmind.google/blog/feed.xml` | 5 |
| `venturebeat_collector.py` | VentureBeat AI | RSS: `venturebeat.com/category/ai/feed/` | 10 |
| `techcrunch_collector.py` | TechCrunch AI | RSS: `techcrunch.com/category/ai/feed/` | 10 |

### Source Weights (14 sources)

| Source | Weight | Tier |
|--------|:------:|------|
| OpenAI | 1.0 | Official blog |
| Anthropic | 1.0 | Official blog |
| Google DeepMind | 1.0 | Official blog |
| Meta AI | 0.95 | Official blog |
| Google AI | 0.95 | Official blog |
| VentureBeat AI | 0.9 | Industry media |
| TechCrunch AI | 0.9 | Industry media |
| Arxiv | 0.9 | Research |
| Hugging Face | 0.75 | Tools/community |
| Hacker News | 0.8 | Community |
| GitHub Trending | 0.7 | Open source |
| Reddit r/MachineLearning | 0.7 | Community |
| 机器之心 | 0.7 | CN media |
| 量子位 | 0.7 | CN media |

### Per-Source Output Limits

| Source Type | Sources | Max per batch |
|-------------|---------|:------------:|
| Official blogs | OpenAI, Anthropic, DeepMind, Meta AI, Hugging Face, Google AI | 2 |
| Industry media | VentureBeat AI, TechCrunch AI | 4 |
| Research/Code | Arxiv, GitHub Trending | 3 |
| Community/Aggregator | HN, Reddit, 机器之心, 量子位 | 2 |

Default fallback: `max_news_per_source: 3` for unlisted sources.

## Scoring Redesign

### New Formula

```
ranking_score = source_weight × 0.25
              + freshness          × 0.25
              + per_source_norm    × 0.20
              + keyword_signal     × 0.15
              + release_boost      (0.10 or 0.15)
              + burst_signal       (0.10)
```

### 1. Per-Source Normalization

Replace global `score/500` with percentile ranking within each source:

| Percentile | Score |
|------------|:-----:|
| Top 5% | 1.0 |
| Top 20% | 0.8 |
| Top 50% | 0.5 |
| Below 50% | 0.3 |
| No score field | 0.6 |

Sources with fewer than 3 items in the candidate pool use a flat 0.6 to avoid unreliable percentile calculation from small samples.

This prevents cross-source score incomparability (e.g., GitHub 10000+ stars vs HN 300 points).

### 2. Official Release Signal

Two-tier detection based on source + title pattern:

**L1 — Version/Model Release (+0.15):**
- Source is an official blog (OpenAI, Anthropic, DeepMind, Meta AI, Google AI)
- Title contains a release verb (introducing, announce, launch, release, available, unveil, present, 发布, 推出, 上线, 开源, 开放)
- Title contains a version/model name (GPT-5, Claude 4, Llama 4, Gemini 3, v2.0, etc.)

**L2 — Feature/Product Release (+0.10):**
- Source is an official blog
- Title contains a release verb
- No version/model name required

**No boost:**
- Third-party sources (VentureBeat, TechCrunch, etc.)
- Official blog posts without release verbs (policy statements, reflections, etc.)

### 3. Cross-Source Burst Detection

Items with title similarity ≥ 0.5 are clustered. Clusters with ≥ 3 distinct sources grant all members +0.10.

This surfaces major news (e.g., GPT-5 launch covered by OpenAI, VentureBeat, TechCrunch, HN simultaneously).

## Config Changes (config.yaml)

```yaml
sources:
  # existing 6 flags unchanged
  meta_ai: true
  huggingface: true
  deepmind: true
  venturebeat: true
  techcrunch: true

analysis:
  max_news_per_day: 15        # was 10
  candidate_pool_size: 45     # was 30
  max_news_per_source: 3      # fallback default
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

## Pipeline (unchanged structure)

```
Collect(14 sources) → AI filter → Deduplicate → Score & Sort → Diversify → Sent filter → Top 15 → Analyze → Push
```

## Files to Change

| File | Change |
|------|--------|
| `config.yaml` | New source flags, limits, batch size |
| `src/aggregator.py` | New scoring formula, per-source norm, release boost, burst detection, per-source limits |
| `src/collectors/meta_ai_collector.py` | New file |
| `src/collectors/huggingface_collector.py` | New file |
| `src/collectors/deepmind_collector.py` | New file |
| `src/collectors/venturebeat_collector.py` | New file |
| `src/collectors/techcrunch_collector.py` | New file |
| `src/main.py` | Register new collectors, pass source_limits |
| `tests/test_aggregator.py` | Tests for new scoring components |
| `README.md` | Update source count, config table |

## Edge Cases

- **Official blogs have no posts**: Industry media (max 4 each) fills slots. No empty batches.
- **All 14 sources produce content**: Round-robin with per-source limits ensures diverse output.
- **Cross-source burst across 10+ sources**: Boost capped at +0.10 regardless of source count.
- **L1 and L2 both match**: L1 takes precedence, no stacking.
- **Sent state filters all candidates**: Falls through to "no news" message.
