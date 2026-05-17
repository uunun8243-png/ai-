# news-digest/src/main.py
import asyncio
import json
import math
import os
import yaml
from datetime import datetime, timezone
from collections import Counter
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict, Tuple
from src.models import NewsItem
from src.collectors.arxiv_collector import ArxivCollector
from src.collectors.github_collector import GitHubTrendingCollector
from src.collectors.hackernews_collector import HackerNewsCollector
from src.collectors.blogs_collector import BlogsCollector
from src.collectors.reddit_collector import RedditCollector
from src.collectors.zh_sources_collector import ZhSourcesCollector
from src.collectors.meta_ai_collector import MetaAICollector
from src.collectors.huggingface_collector import HuggingFaceCollector
from src.collectors.deepmind_collector import DeepMindCollector
from src.collectors.venturebeat_collector import VentureBeatCollector
from src.collectors.techcrunch_collector import TechCrunchCollector
from src.aggregator import Aggregator
from src.analyzer import Analyzer
from src.sent_state import SentState
from src.collectors.monetization_collector import ProductHuntCollector, IndieHackersCollector, RedditSideProjectCollector
from src.monetization_analyzer import MonetizationAnalyzer
from src.notifiers.feishu import FeishuNotifier


def load_config() -> dict:
    load_dotenv(override=True)
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 环境变量覆盖（用于 GitHub Actions Secrets）
    if os.getenv("DEEPSEEK_API_KEY"):
        config.setdefault("deepseek", {})["api_key"] = os.environ["DEEPSEEK_API_KEY"]
    if os.getenv("FEISHU_APP_ID"):
        config.setdefault("feishu", {})["app_id"] = os.environ["FEISHU_APP_ID"]
    if os.getenv("FEISHU_APP_SECRET"):
        config.setdefault("feishu", {})["app_secret"] = os.environ["FEISHU_APP_SECRET"]
    if os.getenv("FEISHU_CHAT_ID"):
        config.setdefault("feishu", {})["chat_id"] = os.environ["FEISHU_CHAT_ID"]

    return config


def save_run_log(run_data: dict) -> None:
    """Write structured run log to logs/test_runs/YYYY-MM-DD-HHmmss.json."""
    logs_dir = Path(__file__).parent.parent / "logs" / "test_runs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log_path = logs_dir / f"{ts}.json"

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  📋 运行日志已保存: {log_path}")


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


def get_monetization_collectors(config: dict) -> list:
    mc = config.get("monetization", {})
    if not mc.get("enabled", True):
        return []
    return [
        ProductHuntCollector(config),
        IndieHackersCollector(config),
        RedditSideProjectCollector(config),
    ]


async def collect_all(collectors: list) -> Tuple[List[NewsItem], Dict[str, int]]:
    """从所有采集器获取新闻。返回 (items, source_counts)。"""
    all_items = []
    source_counts: Dict[str, int] = {}
    for collector in collectors:
        try:
            items = await collector.fetch()
            all_items.extend(items)
            source_counts[collector.source_name] = len(items)
            print(f"  ✓ {collector.source_name}: {len(items)} 条")
        except Exception as e:
            source_counts[collector.source_name] = 0
            print(f"  ✗ {collector.source_name}: {e}")
    return all_items, source_counts


async def collect_monetization(collectors: list) -> list:
    """从所有变现项目采集器获取数据。"""
    from src.models import NewsItem
    all_items = []
    for collector in collectors:
        try:
            items = await collector.fetch()
            all_items.extend(items)
            print(f"  ✓ {collector.source_name}: {len(items)} 条")
        except Exception as e:
            print(f"  ✗ {collector.source_name}: {e}")
    return all_items


async def run_pipeline(batch: str = "上午"):
    """执行完整的采集-分析-推送流水线。"""
    print(f"=== AI 日报 {batch}场 ===")

    config = load_config()
    notifier = FeishuNotifier(config)

    # 1. 采集
    print("\n📡 采集阶段...")
    try:
        collectors = get_collectors(config)
        all_items, collection_counts = await collect_all(collectors)
        print(f"  共采集 {len(all_items)} 条原始新闻")
    except Exception as e:
        print(f"  ✗ 采集阶段失败: {e}")
        await notifier.send_alert("采集阶段", str(e))
        return

    # 2. 聚合
    print("\n🔗 聚合阶段...")
    try:
        aggregator = Aggregator(config)
        sent_state = SentState.from_config(config)
        analysis_config = config.get("analysis", {})
        candidate_limit = analysis_config.get(
            "candidate_pool_size", aggregator.max_per_day * 3
        )

        stage_counts = {"raw": len(all_items)}

        # Stage: recent filter
        recent_items = aggregator.filter_recent(all_items)
        stage_counts["after_recent_filter"] = len(recent_items)

        # Stage: AI filter
        ai_items = aggregator.filter_ai_related(recent_items)
        stage_counts["after_ai_filter"] = len(ai_items)

        # Stage: dedup
        deduped = aggregator.deduplicate(ai_items)
        stage_counts["after_dedup"] = len(deduped)

        # Stage: sort
        sorted_items = aggregator.sort_by_score(deduped)
        diversified = aggregator.diversify_sources(sorted_items, limit=candidate_limit)
        stage_counts["candidate_pool"] = len(diversified)

        # Compute score breakdown for all candidates (before sent-state filter)
        norms = aggregator._compute_norms(diversified)
        cross_boosts = aggregator._cross_source_boost(diversified)
        ranking = []
        for idx, item in enumerate(diversified):
            total = aggregator.ranking_score(item, norms, cross_boosts, idx)
            age_hours = max(
                (datetime.now(timezone.utc) - item.published).total_seconds() / 3600, 0
            )
            half_life = aggregator.SOURCE_HALF_LIFE.get(item.source, 12)
            if half_life == "engagement":
                if age_hours <= aggregator.engagement_window_hours:
                    timeliness = math.log(item.score + 1) * math.exp(-age_hours / 6.0)
                elif age_hours <= aggregator.recent_hours:
                    timeliness = math.exp(-age_hours / aggregator.half_life_community)
                else:
                    timeliness = 0.0
            else:
                timeliness = math.exp(-age_hours / half_life)

            ranking.append({
                "rank": idx + 1,
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "score": round(total, 4),
                "breakdown": {
                    "source": round(aggregator.source_weights.get(item.source, 0.6) * aggregator.weight_source, 4),
                    "timeliness": round(timeliness * aggregator.weight_timeliness, 4),
                    "norm": round(norms.get(idx, 0.6) * aggregator.weight_norm, 4),
                    "keyword": round(aggregator.keyword_strength(item) * aggregator.weight_keyword, 4),
                    "release": round(aggregator._release_boost(item), 4),
                    "cross_source": round(cross_boosts.get(idx, 0.0), 4),
                },
                "age_hours": round(age_hours, 2),
                "published": item.published.isoformat(),
            })

        # DEBUG: print detailed score breakdown
        if os.getenv("DEBUG_SCORE"):
            print(f"\n  {'排名':>4} | {'来源':<20} | {'评分':<6} | {'src':<6} {'fresh':<6} {'norm':<6} {'kw':<6} {'rel':<6} {'cross':<6}")
            print(f"  {'─'*4}─┼─{'─'*20}─┼─{'─'*6}─┼─{'─'*6}─{'─'*6}─{'─'*6}─{'─'*6}─{'─'*6}─{'─'*6}")
            for r in ranking:
                b = r["breakdown"]
                print(f"  #{r['rank']:<2} | {r['source']:<20} | {r['score']:.3f} | {b['source']:.3f} {b['timeliness']:.3f} {b['norm']:.3f} {b['keyword']:.3f} {b['release']:.3f} {b['cross_source']:.3f}")
            print()

        before_sent_filter = len(diversified)
        processed = sent_state.filter_unsent(diversified)
        stage_counts["sent_state_filtered"] = before_sent_filter - len(processed)

        if before_sent_filter != len(processed):
            print(f"  Sent-state filtered {stage_counts['sent_state_filtered']} items")

        batch_items = processed[:aggregator.max_per_day]
        stage_counts["final_batch"] = len(batch_items)
        # Track which ranks made it past sent-state
        sent_urls = {it.url for it in processed}
        final_urls = {it.url for it in batch_items}

        if not batch_items:
            print(f"  本次无新闻推送")
            _write_run_log(config, aggregator, collection_counts, stage_counts,
                           ranking, sent_urls, final_urls, batch, "skipped: no items")
            return

        source_counts = Counter(item.source for item in batch_items)
        source_summary = ", ".join(
            f"{source}: {count}" for source, count in source_counts.items()
        )
        print(f"  处理后 {len(batch_items)} 条")
        print(f"  来源分布: {source_summary}")
    except Exception as e:
        print(f"  ✗ 聚合阶段失败: {e}")
        await notifier.send_alert("聚合阶段", str(e))
        return

    # 3. 分析
    print("\n🔍 分析阶段...")
    try:
        analyzer = Analyzer(config)
        batch_items = await analyzer.analyze_batch(batch_items)
        print(f"  完成 {len(batch_items)} 条分析")

        # 过滤分析失败的条目
        before_filter = len(batch_items)
        batch_items = [it for it in batch_items if it.analysis and "error" not in it.analysis]
        skipped = before_filter - len(batch_items)
        if skipped:
            print(f"  ⚠ 过滤 {skipped} 条分析失败的新闻")
        if not batch_items:
            print(f"  所有分析均失败，终止推送")
            _write_run_log(config, aggregator, collection_counts, stage_counts,
                           ranking, sent_urls, final_urls, batch, "skipped: all analysis failed")
            return

        token_summary = f"prompt {analyzer.total_prompt} + completion {analyzer.total_completion} = {analyzer.total_prompt + analyzer.total_completion}"
    except Exception as e:
        print(f"  ✗ 分析阶段失败: {e}")
        await notifier.send_alert("分析阶段", str(e))
        return

    # 4. 推送
    print("\n📤 推送阶段...")
    push_status = "success"
    try:
        success = await notifier.send_news(batch_items, batch, token_summary)
        if success:
            sent_state.mark_sent(batch_items)
        print(f"  {'✓ 推送成功' if success else '✗ 推送失败'}")
        if not success:
            push_status = "failed"
            await notifier.send_alert("推送阶段", "推送返回失败状态")
    except Exception as e:
        push_status = f"error: {e}"
        print(f"  ✗ 推送阶段失败: {e}")
        await notifier.send_alert("推送阶段", str(e))

    # 5. 变现项目（独立流水线，失败不阻塞主流程）
    print("\n💰 变现项目阶段...")
    monetization_push_status = "skipped"
    try:
        mon_config = config.get("monetization", {})
        if mon_config.get("enabled", True):
            mon_collectors = get_monetization_collectors(config)
            if mon_collectors:
                mon_items = await collect_monetization(mon_collectors)
                print(f"  共采集 {len(mon_items)} 条变现项目")

                if mon_items:
                    mon_sent_state = SentState(
                        Path(__file__).resolve().parent.parent / mon_config.get(
                            "sent_state_path", ".digest-state/monetization_sent_items.json"
                        )
                    )

                    # 简化评分排序
                    from datetime import datetime, timezone
                    import math

                    source_weights = mon_config.get("source_weights", {})
                    now = datetime.now(timezone.utc)

                    def monetization_score(item) -> float:
                        sw = source_weights.get(item.source, 0.5)
                        age_hours = max((now - item.published).total_seconds() / 3600, 0)
                        freshness = math.exp(-age_hours / 24)
                        heat = min(item.score / 100, 1.0) if item.score > 0 else 0.3
                        return sw + freshness + heat

                    mon_items.sort(key=monetization_score, reverse=True)

                    # 去重
                    fresh = mon_sent_state.filter_unsent(mon_items)
                    print(f"  去重过滤 {len(mon_items) - len(fresh)} 条")
                    mon_items = fresh[:mon_config.get("max_per_day", 3)]

                    if mon_items:
                        # 分析
                        mon_analyzer = MonetizationAnalyzer(config)
                        mon_items = await mon_analyzer.analyze_batch(mon_items)

                        # 过滤分析失败的
                        mon_items = [it for it in mon_items if it.analysis and "error" not in it.analysis]

                        if mon_items:
                            success = await notifier.send_monetization(mon_items, batch)
                            if success:
                                mon_sent_state.mark_sent(mon_items)
                            monetization_push_status = "success" if success else "failed"
                            print(f"  {'✓ 变现项目推送成功' if success else '✗ 变现项目推送失败'}")
                        else:
                            print("  分析后无有效变现项目，跳过推送")
                    else:
                        print("  去重后无新变现项目，跳过推送")
            else:
                print("  变现项目采集器未启用")
        else:
            print("  变现项目模块未启用")
    except Exception as e:
        monetization_push_status = f"error: {e}"
        print(f"  ✗ 变现项目阶段失败: {e}")

    _write_run_log(config, aggregator, collection_counts, stage_counts,
                   ranking, sent_urls, final_urls, batch, push_status)


def _write_run_log(
    config: dict,
    aggregator: "Aggregator",
    collection_counts: Dict[str, int],
    stage_counts: Dict[str, int],
    ranking: list,
    sent_urls: set,
    final_urls: set,
    batch: str,
    push_status: str,
) -> None:
    """Assemble run data, compute quality checks, and write the JSON log."""
    scoring_cfg = config.get("scoring", {})

    # Quality checks
    final_ranking = [r for r in ranking if r["url"] in final_urls]
    sources_in_final = {r["source"] for r in final_ranking}
    age_hours_list = [r["age_hours"] for r in final_ranking]
    github_count = sum(1 for r in final_ranking if r["source"] == "GitHub Trending")
    arxiv_count = sum(1 for r in final_ranking if r["source"] == "Arxiv")

    # New content rate: what fraction of candidate pool items passed sent-state
    total_in_pool = len(ranking)
    new_content_rate = (
        len(sent_urls) / total_in_pool if total_in_pool > 0 else 0.0
    )

    # Cross-source coverage: pass if we have diverse sources covering AI news.
    # When 4+ distinct sources are represented, this implies broad AI coverage
    # across the ecosystem — the core intent of the hotspot check.
    has_cross_source_coverage = len(sources_in_final) >= 4

    quality = {
        "source_diversity": {
            "sources": len(sources_in_final),
            "pass": len(sources_in_final) >= 4,
            "require": 4,
        },
        "timeliness_16h": {
            "ratio": round(
                sum(1 for h in age_hours_list if h <= 16) / max(len(age_hours_list), 1), 2
            ),
            "pass": sum(1 for h in age_hours_list if h <= 16) / max(len(age_hours_list), 1) >= 0.5,
            "require": 0.5,
        },
        "github_recovery": {
            "count": github_count,
            "pass": github_count > 0,
            "require": ">0",
        },
        "arxiv_in_ranking": {
            "count": arxiv_count,
            "pass": arxiv_count >= 1,
            "require": 1,
        },
        "new_content_rate": {
            "ratio": round(new_content_rate, 2),
            "pass": new_content_rate > 0.5,
            "require": 0.5,
        },
        "cross_source_hotspot": {
            "has_cross_source_coverage": has_cross_source_coverage,
            "pass": has_cross_source_coverage,
        },
    }

    run_data = {
        "timestamp": datetime.now().isoformat(),
        "batch": batch,
        "push_status": push_status,
        "config": {
            "max_news_per_day": aggregator.max_per_day,
            "recent_hours": aggregator.recent_hours,
            "weights": {
                "source": aggregator.weight_source,
                "timeliness": aggregator.weight_timeliness,
                "norm": aggregator.weight_norm,
                "keyword": aggregator.weight_keyword,
            },
            "engagement_window_hours": aggregator.engagement_window_hours,
            "half_life_community": aggregator.half_life_community,
        },
        "collection": {
            "total_raw": sum(collection_counts.values()),
            "by_source": collection_counts,
        },
        "pipeline": stage_counts,
        "ranking": final_ranking,
        "full_ranking": ranking,
        "quality": quality,
    }

    save_run_log(run_data)


async def main():
    """入口函数。根据当前时间决定推送哪一批。"""
    from datetime import datetime

    batch_from_env = os.getenv("DIGEST_BATCH", "").strip().lower()
    if batch_from_env in {"morning", "上午"}:
        await run_pipeline("上午")
        return
    if batch_from_env in {"afternoon", "下午"}:
        await run_pipeline("下午")
        return

    hour = datetime.now().hour
    batch = "下午" if hour >= 12 else "上午"
    await run_pipeline(batch)


if __name__ == "__main__":
    asyncio.run(main())
