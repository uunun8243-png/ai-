import httpx
from datetime import datetime, timezone, timedelta
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class GitHubTrendingCollector(BaseCollector):
    source_key = "github_trending"
    source_name = "GitHub Trending"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []

        url = "https://api.github.com/search/repositories"
        params = {
            "q": "created:>={date} (topic:ai OR topic:llm OR topic:machine-learning)",
            "sort": "stars",
            "per_page": 10,
        }
        # 用过去 7 天的日期
        date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        params["q"] = params["q"].format(date=date)

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
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
