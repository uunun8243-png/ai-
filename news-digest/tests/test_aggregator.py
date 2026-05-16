# news-digest/tests/test_aggregator.py
from datetime import datetime, timezone, timedelta
from src.models import NewsItem
from src.aggregator import Aggregator


def make_item(title: str, score: float = 0, hours_ago: int = 0) -> NewsItem:
    return NewsItem(
        title=title,
        url=f"https://example.com/{title}",
        source="Test",
        published=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        summary=f"Summary of {title}",
        score=score,
    )


def make_ai_item(title: str, source: str, score: float = 0) -> NewsItem:
    item = make_item(title, score=score)
    item.source = source
    return item


def test_deduplicate_exact_duplicates():
    agg = Aggregator({"analysis": {}})
    items = [make_item("Same Title"), make_item("Same Title")]
    result = agg.deduplicate(items)
    assert len(result) == 1


def test_deduplicate_similar_titles():
    agg = Aggregator({"analysis": {}})
    items = [
        make_item("GPT-5 发布：OpenAI 下一代模型"),
        make_item("GPT-5 正式发布：OpenAI 最新模型来了"),
    ]
    result = agg.deduplicate(items)
    assert len(result) == 1


def test_deduplicate_different_titles():
    agg = Aggregator({"analysis": {}})
    items = [
        make_item("GPT-5 发布"),
        make_item("Claude 4.7 发布"),
    ]
    result = agg.deduplicate(items)
    assert len(result) == 2


def test_sort_by_score():
    agg = Aggregator({"analysis": {}})
    # With the new percentile-based normalization, items from the same source
    # are ranked by score percentiles: >=95% -> 1.0, >=80% -> 0.8, >=50% -> 0.5, else 0.3.
    # Use scores spread enough to produce distinct percentile buckets.
    items = [
        make_item("A", score=1),
        make_item("B", score=500),
        make_item("C", score=10),
        make_item("D", score=200),
        make_item("E", score=50),
    ]
    result = agg.sort_by_score(items)
    # B(500) in 80th+ pct -> norm 0.8, D(200) in 50th+ pct -> norm 0.5,
    # E(50), C(10), A(1) in bottom 50% -> norm 0.3, preserved in input order.
    assert [i.title for i in result] == ["B", "D", "A", "C", "E"]


def test_diversify_sources_limits_single_source():
    agg = Aggregator({"analysis": {"max_news_per_day": 10, "max_news_per_source": 3}})
    items = [
        make_ai_item(f"Arxiv GPT paper {i}", "Arxiv", score=100 - i)
        for i in range(8)
    ]
    result = agg.diversify_sources(items)
    assert len(result) == 3
    assert all(item.source == "Arxiv" for item in result)


def test_diversify_sources_round_robins_sources():
    agg = Aggregator({"analysis": {"max_news_per_day": 6, "max_news_per_source": 3}})
    items = [
        make_ai_item("Arxiv GPT paper 1", "Arxiv", score=100),
        make_ai_item("Arxiv GPT paper 2", "Arxiv", score=99),
        make_ai_item("Arxiv GPT paper 3", "Arxiv", score=98),
        make_ai_item("OpenAI GPT release", "OpenAI", score=80),
        make_ai_item("OpenAI agent update", "OpenAI", score=79),
        make_ai_item("Hacker News LLM discussion", "Hacker News", score=60),
    ]
    result = agg.diversify_sources(items)
    assert [item.source for item in result] == [
        "Arxiv",
        "OpenAI",
        "Hacker News",
        "Arxiv",
        "OpenAI",
        "Arxiv",
    ]


def test_filter_recent():
    agg = Aggregator({"analysis": {}})
    items = [make_item("Old", hours_ago=72), make_item("New", hours_ago=1)]
    result = agg.filter_recent(items, hours=48)
    assert len(result) == 1
    assert result[0].title == "New"


def test_filter_recent_uses_configured_window_by_default():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    items = [
        make_item("OpenAI old GPT update", hours_ago=30),
        make_item("OpenAI fresh GPT update", hours_ago=23),
    ]
    result = agg.filter_recent(items)
    assert [item.title for item in result] == ["OpenAI fresh GPT update"]


def test_ranking_score_normalizes_raw_source_scores():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    github_item = make_ai_item(
        "Daily repository roundup",
        "GitHub Trending",
        score=100000,
    )
    github_item.published = datetime.now(timezone.utc) - timedelta(hours=12)

    hn_item = make_ai_item(
        "GPT LLM agents improve AI workflows",
        "Hacker News",
        score=100,
    )

    items = [github_item, hn_item]
    norms = agg._compute_norms(items)
    boosts = agg._burst_detect(items)
    score_g = agg.ranking_score(github_item, norms, boosts, 0)
    score_h = agg.ranking_score(hn_item, norms, boosts, 1)
    assert score_h > score_g
    assert agg.sort_by_score([github_item, hn_item])[0] == hn_item


def test_filter_ai_related_rejects_unrelated_title_with_ai_substring():
    agg = Aggregator({"analysis": {}})
    item = make_item("Heavy rain delays railway mail service")
    item.summary = "A weather update unrelated to artificial intelligence."
    item.summary = "A weather update unrelated to software."
    assert agg.filter_ai_related([item]) == []


def test_filter_ai_related_accepts_chinese_ai_terms():
    agg = Aggregator({"analysis": {}})
    item = make_item("国产大模型发布多模态推理能力")
    assert agg.filter_ai_related([item]) == [item]


def test_filter_ai_related_keeps_trusted_ai_sources():
    agg = Aggregator({"analysis": {}})
    item = make_item("Release notes")
    item.source = "OpenAI"
    assert agg.filter_ai_related([item]) == [item]


def test_process_respects_max_per_day():
    agg = Aggregator({"analysis": {"max_news_per_day": 3, "max_news_per_source": 3}})
    titles = [
        "OpenAI releases GPT audio model",
        "Claude adds agent workflow tools",
        "Gemini improves multimodal reasoning",
        "DeepSeek publishes coding benchmark",
        "LLM inference costs continue falling",
        "Machine learning compiler speeds training",
        "RAG system improves enterprise search",
        "AI copilot launches for developers",
        "Transformer architecture gets memory upgrade",
        "Neural network accelerator announced",
    ]
    items = [make_item(title, score=i) for i, title in enumerate(titles)]
    result = agg.process(items)
    assert len(result) == 3


def test_process_can_return_larger_candidate_pool():
    agg = Aggregator({"analysis": {"max_news_per_day": 3, "max_news_per_source": 10}})
    titles = [
        "OpenAI releases GPT audio model",
        "Claude adds agent workflow tools",
        "Gemini improves multimodal reasoning",
        "DeepSeek publishes coding benchmark",
        "LLM inference costs continue falling",
    ]
    items = [make_item(title, score=i) for i, title in enumerate(titles)]
    result = agg.process(items, limit=5)
    assert len(result) == 5


def test_split_batches():
    agg = Aggregator({"analysis": {}})
    items = [make_item(f"Item {i}") for i in range(15)]
    morning, afternoon = agg.split_batches(items)
    assert len(morning) == 10
    assert len(afternoon) == 5


def test_split_batches_no_overflow():
    agg = Aggregator({"analysis": {}})
    items = [make_item(f"Item {i}") for i in range(5)]
    morning, afternoon = agg.split_batches(items)
    assert len(morning) == 5
    assert afternoon == []


def test_per_source_norm_top_item_gets_near_top_bucket():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    # With 4 items: pcts = 0, 0.25, 0.50, 0.75 → scores 0.3, 0.3, 0.5, 0.5
    items = [
        make_ai_item("Top HN post", "Hacker News", score=500),
        make_ai_item("Mid HN post", "Hacker News", score=200),
        make_ai_item("Mid2 HN post", "Hacker News", score=150),
        make_ai_item("Low HN post", "Hacker News", score=50),
    ]
    norms = agg._compute_norms(items)
    assert norms[0] == 0.5  # 75th pct = 0.5 bucket


def test_per_source_norm_large_set_reaches_top_bucket():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    # 25 items means top item at pct 0.96 → 95th+ → 1.0
    items = [
        make_ai_item(f"Item {i}", "Hacker News", score=i * 10)
        for i in range(25)
    ]
    norms = agg._compute_norms(items)
    # Highest score (240) is at the 96th percentile
    top_idx = [i for i, n in norms.items() if n == 1.0]
    assert len(top_idx) >= 1


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
    # 25 items per source → top item at 96th pct → 1.0
    items = []
    for i in range(25):
        items.append(make_ai_item(f"GitHub repo {i}", "GitHub Trending", score=i * 10))
    for i in range(25):
        items.append(make_ai_item(f"HN post {i}", "Hacker News", score=i * 10))

    norms = agg._compute_norms(items)
    # Top GitHub (score 240) → norms idx at score 240
    top_gh_idx = next(i for i in range(25) if items[i].score == 240)
    assert norms[top_gh_idx] == 1.0

    # Top HN (score 240) → 1.0
    top_hn_idx = next(i for i in range(25, 50) if items[i].score == 240)
    assert norms[top_hn_idx] == 1.0

    # Lowest GitHub (score 0) → excluded from norms (score <= 0)
    low_gh_idx = next(i for i in range(25) if items[i].score == 0)
    assert low_gh_idx not in norms  # items with score 0 are omitted


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


def test_burst_detect_three_sources_boosts():
    agg = Aggregator({"analysis": {}})
    # Use near-identical titles to pass SequenceMatcher >= 0.5
    items = [
        make_ai_item("OpenAI announces GPT-5 launch with new features", "OpenAI", score=0),
        make_ai_item("OpenAI announces GPT-5 launch with new features", "VentureBeat AI", score=0),
        make_ai_item("OpenAI announces GPT-5 launch with new features", "TechCrunch AI", score=0),
        make_ai_item("Some unrelated Arxiv paper about math", "Arxiv", score=0),
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


def test_ranking_score_prefers_official_release_with_burst():
    agg = Aggregator({"analysis": {"recent_hours": 24}})
    now = datetime.now(timezone.utc)

    openai_item = make_ai_item("Introducing GPT-5", "OpenAI", score=0)
    openai_item.published = now - timedelta(hours=1)

    hn_item = make_ai_item("Show HN: my AI agent side project", "Hacker News", score=300)
    hn_item.published = now - timedelta(hours=1)

    items = [openai_item, hn_item]
    norms = agg._compute_norms(items)
    boosts = agg._burst_detect(items)
    score_o = agg.ranking_score(openai_item, norms, boosts, 0)
    score_h = agg.ranking_score(hn_item, norms, boosts, 1)
    assert score_o > score_h


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
    vb_count = sum(1 for i in result if i.source == "VentureBeat AI")
    arxiv_count = sum(1 for i in result if i.source == "Arxiv")
    assert vb_count == 2
    assert arxiv_count == 1
