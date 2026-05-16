# news-digest/src/sent_state.py
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Set, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.models import NewsItem


TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


class SentState:
    """Local record of items that were already pushed."""

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._fingerprints = self._load()

    @classmethod
    def from_config(cls, config: dict) -> "SentState":
        analysis_config = config.get("analysis", {})
        configured_path = analysis_config.get(
            "sent_state_path", ".digest-state/sent_items.json"
        )
        path = Path(configured_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        return cls(path)

    @staticmethod
    def normalize_url(url: str) -> str:
        if not url:
            return ""

        parsed = urlsplit(url.strip())
        scheme = (parsed.scheme or "https").lower()
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = parsed.path.rstrip("/") or "/"
        query = urlencode(
            sorted(
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.lower() not in TRACKING_PARAMS
            )
        )
        return urlunsplit((scheme, netloc, path, query, ""))

    @staticmethod
    def normalize_title(title: str) -> str:
        title = (title or "").lower()
        title = re.sub(r"[^\w\s]", " ", title, flags=re.UNICODE)
        return re.sub(r"\s+", " ", title).strip()

    @classmethod
    def fingerprint(cls, item: NewsItem) -> str:
        stable_text = f"{cls.normalize_url(item.url)}\n{cls.normalize_title(item.title)}"
        return hashlib.sha256(stable_text.encode("utf-8")).hexdigest()

    @classmethod
    def fingerprints(cls, item: NewsItem) -> set[str]:
        values = []
        normalized_url = cls.normalize_url(item.url)
        normalized_title = cls.normalize_title(item.title)
        if normalized_url:
            values.append(f"url:{normalized_url}")
        if normalized_title:
            values.append(f"title:{normalized_title}")
        if normalized_url and normalized_title:
            values.append(f"item:{normalized_url}\n{normalized_title}")
            values.append(f"{normalized_url}\n{normalized_title}")
        return {
            hashlib.sha256(value.encode("utf-8")).hexdigest()
            for value in values
        }

    def filter_unsent(self, items: Iterable[NewsItem]) -> list[NewsItem]:
        return [
            item
            for item in items
            if self.fingerprints(item).isdisjoint(self._fingerprints)
        ]

    def mark_sent(self, items: Iterable[NewsItem]) -> None:
        for item in items:
            self._fingerprints.update(self.fingerprints(item))
        self.save()

    def _load(self) -> Set[str]:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return set()

        if isinstance(data, dict):
            fingerprints = data.get("fingerprints", [])
        else:
            fingerprints = data

        if not isinstance(fingerprints, list):
            return set()
        return {fp for fp in fingerprints if isinstance(fp, str)}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fingerprints": sorted(self._fingerprints)}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
