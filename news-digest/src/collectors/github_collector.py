import os
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
        date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        # 搜索最近7天创建、有AI关键词且star>1000的仓库
        params = {
            "q": f"created:>={date} stars:>1000 (ai OR llm OR generative OR topic:ai OR topic:llm OR topic:machine-learning)",
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
