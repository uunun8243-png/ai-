# news-digest/src/sent_state.py
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
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
    """Local record of items that were already pushed.

    Fingerprints are stored with timestamps.  Entries older than
    *retention_hours* are pruned on load (default 48 h).
    """

    retention_hours = 48

    def __init__(self, path: Union[str, Path], retention_hours: int = 48):
        self.path = Path(path)
        self.retention_hours = retention_hours
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
        retention = analysis_config.get("sent_state_retention_hours", 48)
        return cls(path, retention_hours=retention)

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
        known = set(self._fingerprints)
        return [
            item
            for item in items
            if self.fingerprints(item).isdisjoint(known)
        ]

    def mark_sent(self, items: Iterable[NewsItem]) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        for item in items:
            for fp in self.fingerprints(item):
                self._fingerprints[fp] = now_iso
        self.save()

    def _load(self) -> dict:
        """Load fingerprints, returning {hash: timestamp_iso_or_none, ...}.

        Supports both the new dict format and the legacy list format.
        Entries older than *retention_hours* are pruned.
        """
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

        raw = data.get("fingerprints") if isinstance(data, dict) else data

        if isinstance(raw, dict):
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
            result = {}
            for fp, ts_str in raw.items():
                if not isinstance(fp, str):
                    continue
                if isinstance(ts_str, str):
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        if ts >= cutoff:
                            result[fp] = ts_str
                    except (ValueError, TypeError):
                        continue
                else:
                    # Legacy entry without a timestamp — keep it forever
                    result[fp] = None
            return result
        elif isinstance(raw, list):
            # Legacy list format — migrate to dict with null timestamps
            return {fp: None for fp in raw if isinstance(fp, str)}
        return {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fingerprints": self._fingerprints}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
