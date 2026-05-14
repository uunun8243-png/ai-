# news-digest/src/main.py
import asyncio
import os
import yaml
from pathlib import Path
from typing import List
from src.models import NewsItem
from src.collectors.arxiv_collector import ArxivCollector
from src.collectors.github_collector import GitHubTrendingCollector
from src.collectors.hackernews_collector import HackerNewsCollector
from src.collectors.blogs_collector import BlogsCollector
from src.collectors.reddit_collector import RedditCollector
from src.collectors.zh_sources_collector import ZhSourcesCollector
from src.aggregator import Aggregator
from src.analyzer import Analyzer
from src.notifiers.feishu import FeishuNotifier


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 环境变量覆盖（用于 GitHub Actions Secrets）
    if os.getenv("DEEPSEEK_API_KEY"):
        config.setdefault("deepseek", {})["api_key"] = os.environ["DEEPSEEK_API_KEY"]
    if os.getenv("FEISHU_WEBHOOK_URL"):
        config.setdefault("feishu", {})["webhook_url"] = os.environ["FEISHU_WEBHOOK_URL"]

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

    # 1. 采集
    print("\n📡 采集阶段...")
    collectors = get_collectors(config)
    all_items = await collect_all(collectors)
    print(f"  共采集 {len(all_items)} 条原始新闻")

    # 2. 聚合
    print("\n🔗 聚合阶段...")
    aggregator = Aggregator(config)
    processed = aggregator.process(all_items)
    morning, afternoon = aggregator.split_batches(processed)

    if batch == "上午":
        batch_items = morning
    else:
        batch_items = afternoon

    if not batch_items:
        print(f"  本次无新闻推送")
        return

    print(f"  处理后 {len(batch_items)} 条")

    # 3. 分析
    print("\n🔍 分析阶段...")
    analyzer = Analyzer(config)
    batch_items = await analyzer.analyze_batch(batch_items)
    print(f"  完成 {len(batch_items)} 条分析")

    # 4. 推送
    print("\n📤 推送阶段...")
    notifier = FeishuNotifier(config)
    success = await notifier.send_news(batch_items, batch)
    print(f"  {'✓ 推送成功' if success else '✗ 推送失败'}")


async def main():
    """入口函数。根据当前时间决定推送哪一批。"""
    from datetime import datetime
    hour = datetime.now().hour
    batch = "下午" if hour >= 12 else "上午"
    await run_pipeline(batch)


if __name__ == "__main__":
    asyncio.run(main())
