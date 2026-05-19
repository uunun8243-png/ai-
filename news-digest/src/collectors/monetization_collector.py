import httpx
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector

GRAPHQL_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"
POSTS_QUERY = """
query($first: Int!, $topic: String) {
  posts(first: $first, order: VOTES, topic: $topic) {
    edges {
      node {
        id
        name
        tagline
        votesCount
        commentsCount
        createdAt
        url
      }
    }
  }
}
"""


def _score_product(item: NewsItem) -> float:
    """Combined score = votes + comments, used for sorting after filters."""
    return (item.score or 0) + (getattr(item, "comments_count", 0) or 0)


class ProductHuntCollector(BaseCollector):
    """采集 Product Hunt AI 分类热门产品（GraphQL API）。"""
    source_key = "product_hunt"
    source_name = "Product Hunt"

    def __init__(self, config: dict):
        super().__init__(config)
        mon_cfg = config.get("monetization", {})
        self.api_key = mon_cfg.get("api_key", "") or ""
        self.topic = mon_cfg.get("product_hunt_topic", "ai")
        self.top_n = mon_cfg.get("product_hunt_top_n", 10)
        self.min_votes = mon_cfg.get("product_hunt_min_votes", 300)
        # Exclude items with abnormally high votes-to-comments ratio
        self.max_vote_comment_ratio = mon_cfg.get("product_hunt_max_vote_comment_ratio", 30)

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []
        if not self.api_key:
            print("  ⚠ Product Hunt API key not configured, skipping")
            return []

        items = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    GRAPHQL_ENDPOINT,
                    json={
                        "query": POSTS_QUERY,
                        "variables": {"first": self.top_n, "topic": self.topic},
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()

                if "errors" in data:
                    print(f"  ⚠ Product Hunt API error: {data['errors']}")
                    return []

                edges = data.get("data", {}).get("posts", {}).get("edges", [])
            except Exception as e:
                print(f"  ⚠ Product Hunt 采集失败: {e}")
                return []

            for edge in edges:
                node = edge.get("node", {})
                name = node.get("name", "").strip()
                if not name:
                    continue

                votes = node.get("votesCount", 0) or 0
                comments = node.get("commentsCount", 0) or 0
                tagline = node.get("tagline", "") or ""
                url = node.get("url", "") or ""
                created = node.get("createdAt", "")

                # --- Quality filters ---
                # 1. Minimum votes threshold
                if votes < self.min_votes:
                    continue

                # 2. High votes but abnormally low engagement
                if votes > 100 and comments == 0:
                    continue
                if comments > 0 and votes / comments > self.max_vote_comment_ratio:
                    continue

                published = datetime.now(timezone.utc)
                if created:
                    try:
                        published = datetime.fromisoformat(
                            created.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        pass

                item = NewsItem(
                    title=name,
                    url=url,
                    source=self.source_name,
                    published=published,
                    summary=tagline or name,
                    score=votes,
                )
                item.comments_count = comments
                items.append(item)

        # Sort by combined score descending
        items.sort(key=_score_product, reverse=True)
        return items
