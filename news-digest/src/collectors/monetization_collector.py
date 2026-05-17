import httpx
from datetime import datetime, timezone
from typing import List
from src.models import NewsItem
from src.collectors.base import BaseCollector


class ProductHuntCollector(BaseCollector):
    """采集 Product Hunt AI 分类热门产品。"""
    source_key = "product_hunt"
    source_name = "Product Hunt"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []
        items = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    "https://www.producthunt.com/feed?category=artificial-intelligence",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
                posts = data.get("posts", [])[:10]
                for post in posts:
                    title = post.get("name", "")
                    if not title:
                        continue
                    tagline = post.get("tagline", "")
                    url = post.get("url", post.get("discussion_url", ""))
                    votes = post.get("votes_count", 0)
                    published_str = post.get("created_at", "")
                    published = datetime.now(timezone.utc)
                    if published_str:
                        try:
                            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            pass
                    items.append(NewsItem(
                        title=title,
                        url=url,
                        source=self.source_name,
                        published=published,
                        summary=tagline,
                        score=votes,
                    ))
            except Exception as e:
                print(f"  ⚠ Product Hunt 采集失败: {e}")
        return items


class IndieHackersCollector(BaseCollector):
    """采集 IndieHackers 最新帖子。"""
    source_key = "indie_hackers"
    source_name = "IndieHackers"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []
        items = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    "https://www.indiehackers.com/rss.xml",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.content)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall("atom:entry", ns) or root.findall("entry", ns)
                for entry in entries[:15]:
                    title_el = entry.find("atom:title", ns) or entry.find("title", ns)
                    link_el = entry.find("atom:link", ns) or entry.find("link", ns)
                    summary_el = entry.find("atom:summary", ns) or entry.find("summary", ns)
                    published_el = entry.find("atom:published", ns) or entry.find("published", ns)
                    if title_el is None or title_el.text is None:
                        continue
                    title = title_el.text
                    url = link_el.get("href", "") if link_el is not None else ""
                    summary = summary_el.text[:500] if summary_el is not None and summary_el.text else title
                    published = datetime.now(timezone.utc)
                    if published_el is not None and published_el.text:
                        try:
                            published = datetime.fromisoformat(published_el.text.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            pass
                    items.append(NewsItem(
                        title=title,
                        url=url,
                        source=self.source_name,
                        published=published,
                        summary=summary,
                        score=0,
                    ))
            except Exception as e:
                print(f"  ⚠ IndieHackers 采集失败: {e}")
        return items


class RedditSideProjectCollector(BaseCollector):
    """采集 Reddit r/SideProject + r/SaaS 热门帖子。"""
    source_key = "reddit"
    source_name = "Reddit"

    async def fetch(self) -> List[NewsItem]:
        if not self.enabled:
            return []
        items = []
        subreddits = ["SideProject", "SaaS", "Entrepreneur"]
        async with httpx.AsyncClient() as client:
            for sub in subreddits:
                try:
                    resp = await client.get(
                        f"https://www.reddit.com/r/{sub}/hot.json?limit=10",
                        headers={"User-Agent": "Mozilla/5.0 (by /u/news-digest-bot)"},
                        timeout=15.0,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        title = post.get("title", "")
                        if not title:
                            continue
                        url = post.get("url", "")
                        selftext = (post.get("selftext", "") or "")[:500]
                        score = post.get("score", 0)
                        created = post.get("created_utc", 0)
                        published = datetime.fromtimestamp(created, tz=timezone.utc) if created else datetime.now(timezone.utc)
                        items.append(NewsItem(
                            title=title,
                            url=url,
                            source=self.source_name,
                            published=published,
                            summary=selftext or title,
                            score=score,
                        ))
                except Exception as e:
                    print(f"  ⚠ Reddit r/{sub} 采集失败: {e}")
        return items
