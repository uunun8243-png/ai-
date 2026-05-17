import os
import httpx
from datetime import datetime, timezone, timedelta
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class GitHubTrendingCollector(BaseCollector):
    source_key = "github_trending"
    source_name = "GitHub Trending"

    def __init__(self, config: dict):
        super().__init__(config)
        github_cfg = config.get("scoring", {}).get("github", {})
        self.min_stars = github_cfg.get("min_stars", 300)
        self.time_window_days = github_cfg.get("time_window_days", 7)
        self.query_keywords = github_cfg.get("query_keywords", "ai")

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        url = "https://api.github.com/search/repositories"
        date = (datetime.now(timezone.utc) - timedelta(days=self.time_window_days)).strftime("%Y-%m-%d")
        query = f"created:>={date} stars:>={self.min_stars} {self.query_keywords}"
        params = {
            "q": query,
            "sort": "stars",
            "per_page": 15,
        }

        headers = {}
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        items = []
        for repo in data.get("items", []):
            items.append(NewsItem(
                title=f"[GitHub] {repo['full_name']}: {repo['description'] or 'No description'}",
                url=repo["html_url"],
                source=self.source_name,
                published=datetime.strptime(repo["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc),
                summary=repo.get("description") or "",
                category="开源项目",
                score=repo.get("stargazers_count", 0),
            ))

        return items
