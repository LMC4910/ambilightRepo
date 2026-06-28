"""Tests for the GitHub SQLite store: dedup, ring buffer, poll cursors, cache."""

from ambilight.integrations.github.store import GithubStore
from ambilight.integrations.github.models import GithubEvent


def _store(tmp_path):
    return GithubStore(path=tmp_path / "github.db")


def _ev(i):
    return GithubEvent(id=f"e{i}", event_type="push", action="pushed",
                       title=f"event {i}", timestamp=float(i))


def test_mark_seen_dedup(tmp_path):
    s = _store(tmp_path)
    assert s.mark_seen("abc") is True       # new
    assert s.mark_seen("abc") is False      # already seen
    assert s.mark_seen("") is False         # empty id never processed
    s.close()


def test_recent_events_newest_first(tmp_path):
    s = _store(tmp_path)
    for i in range(5):
        s.add_event(_ev(i))
    recent = s.recent(limit=3)
    assert [e["id"] for e in recent] == ["e4", "e3", "e2"]
    s.close()


def test_recent_ring_buffer_cap(tmp_path, monkeypatch):
    import ambilight.integrations.github.store as store_mod
    monkeypatch.setattr(store_mod, "_RECENT_CAP", 3)
    s = _store(tmp_path)
    for i in range(6):
        s.add_event(_ev(i))
    recent = s.recent(limit=100)
    assert len(recent) == 3
    assert [e["id"] for e in recent] == ["e5", "e4", "e3"]
    s.close()


def test_poll_state_roundtrip(tmp_path):
    s = _store(tmp_path)
    assert s.get_poll_state("notifications")["etag"] is None
    s.set_poll_state("notifications", etag='W/"abc"', last_modified="Mon")
    state = s.get_poll_state("notifications")
    assert state["etag"] == 'W/"abc"'
    assert state["last_modified"] == "Mon"
    s.close()


def test_cache_roundtrip(tmp_path):
    s = _store(tmp_path)
    assert s.get_cache("orgs") is None
    s.set_cache("orgs", [{"login": "acme"}])
    assert s.get_cache("orgs") == [{"login": "acme"}]
    s.close()
