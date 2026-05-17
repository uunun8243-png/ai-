import httpx
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class RedditCollector(BaseCollector):
    source_key = "reddit_ml"
    source_name = "Reddit r/MachineLearning"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        url = "https://www.reddit.com/r/MachineLearning/hot.json?limit=15"

        async with httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/json,*/*",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                self.log_error(f"Reddit API request failed: {exc}")
                return []

        try:
            data = response.json()
        except ValueError as exc:
            self.log_error(f"Reddit JSON parse failed: {exc}")
            return []

        items: List[NewsItem] = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if not post:
                continue

            title = post.get("title", "")
            permalink = post.get("permalink", "")
            external_url = post.get("url", "")

            # Use external URL if it points outside Reddit, otherwise fall back to permalink
            if external_url and not external_url.startswith("https://www.reddit.com"):
                item_url = external_url
            else:
                item_url = f"https://www.reddit.com{permalink}" if permalink else external_url

            score = float(post.get("score", 0))
            num_comments = post.get("num_comments", 0)
            selftext = post.get("selftext", "") or ""

            # Build summary with comment count prefix
            summary_parts = []
            if num_comments > 0:
                summary_parts.append(f"[comments: {num_comments}]")
            if selftext:
                summary_parts.append(selftext[:500])
            summary = " ".join(summary_parts)

            # Convert Unix timestamp to datetime
            created_utc = post.get("created_utc")
            if created_utc:
                published = datetime.fromtimestamp(created_utc, tz=timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            items.append(NewsItem(
                title=title,
                url=item_url,
                source=self.source_name,
                published=published,
                summary=summary,
                category="行业动态",
                score=score,
            ))

        return items

    def log_error(self, message: str) -> None:
        """Log an error message. Override to integrate with your logging framework."""
        print(f"[{self.source_name}] {message}")
