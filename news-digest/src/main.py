# news-digest/src/main.py
import asyncio
import os
import yaml
from collections import Counter
from dotenv import load_dotenv
from pathlib import Path
from typing import List
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


async def collect_all(collectors: list) -> List[NewsItem]:
    """从所有采集器获取新闻。"""
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
        all_items = await collect_all(collectors)
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
        processed = aggregator.process(all_items, limit=candidate_limit)
        before_sent_filter = len(processed)
        processed = sent_state.filter_unsent(processed)
        if before_sent_filter != len(processed):
            print(f"  Sent-state filtered {before_sent_filter - len(processed)} items")

        batch_items = processed[:aggregator.max_per_day]

        if not batch_items:
            print(f"  本次无新闻推送")
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
    except Exception as e:
        print(f"  ✗ 分析阶段失败: {e}")
        await notifier.send_alert("分析阶段", str(e))
        return

    # 4. 推送
    print("\n📤 推送阶段...")
    try:
        success = await notifier.send_news(batch_items, batch)
        if success:
            sent_state.mark_sent(batch_items)
        print(f"  {'✓ 推送成功' if success else '✗ 推送失败'}")
        if not success:
            await notifier.send_alert("推送阶段", "推送返回失败状态")
    except Exception as e:
        print(f"  ✗ 推送阶段失败: {e}")
        await notifier.send_alert("推送阶段", str(e))


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
