import json
from datetime import datetime, timezone

from src.models import NewsItem
from src.sent_state import SentState


class MemorySentState(SentState):
    def __init__(self, initial=None):
        self.saved_payload = None
        super().__init__("memory.json")
        if isinstance(initial, dict):
            self._fingerprints = dict(initial)
        elif isinstance(initial, (list, set)):
            self._fingerprints = {fp: None for fp in initial}
        else:
            self._fingerprints = {}

    def _load(self):
        return {}

    def save(self):
        self.saved_payload = {"fingerprints": dict(self._fingerprints)}


def make_item(title: str, url: str) -> NewsItem:
    return NewsItem(
        title=title,
        url=url,
        source="Test",
        published=datetime.now(timezone.utc),
        summary="summary",
    )


def test_fingerprint_normalizes_url_and_title():
    item = make_item(
        "  OpenAI Releases GPT-5! ",
        "HTTPS://www.Example.com/news/?utm_source=x&id=1#comments",
    )
    same_item = make_item(
        "openai releases gpt 5",
        "https://example.com/news?id=1",
    )

    assert SentState.fingerprint(item) == SentState.fingerprint(same_item)


def test_filter_unsent_and_mark_sent_round_trip():
    state = MemorySentState()
    sent = make_item("OpenAI GPT release", "https://example.com/a")
    fresh = make_item("Anthropic Claude release", "https://example.com/b")

    state.mark_sent([sent])

    reloaded = MemorySentState(state.saved_payload["fingerprints"])
    assert reloaded.filter_unsent([sent, fresh]) == [fresh]
    assert SentState.fingerprint(sent) in state.saved_payload["fingerprints"]


def test_filter_unsent_matches_same_title_from_different_url():
    state = MemorySentState()
    sent = make_item("OpenAI GPT release", "https://example.com/a")
    duplicate = make_item("openai gpt release", "https://another.example/news")

    state.mark_sent([sent])

    reloaded = MemorySentState(state.saved_payload["fingerprints"])
    assert reloaded.filter_unsent([duplicate]) == []


def test_filter_unsent_matches_same_url_with_different_title():
    state = MemorySentState()
    sent = make_item("OpenAI GPT release", "https://example.com/a?utm_source=x")
    duplicate = make_item("OpenAI announces model", "https://www.example.com/a")

    state.mark_sent([sent])

    reloaded = MemorySentState(state.saved_payload["fingerprints"])
    assert reloaded.filter_unsent([duplicate]) == []


def test_corrupt_state_file_is_treated_as_empty(monkeypatch):
    def raise_bad_json(*args, **kwargs):
        raise json.JSONDecodeError("bad", "{", 0)

    monkeypatch.setattr("pathlib.Path.open", raise_bad_json)
    state = SentState("broken.json")
    item = make_item("OpenAI GPT release", "https://example.com/a")

    assert state.filter_unsent([item]) == [item]
