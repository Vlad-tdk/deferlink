from __future__ import annotations

from app.deeplink_handler import DeepLinkHandler


def test_resolve_matching_session_retries_after_atomic_conflict(monkeypatch):
    handler = DeepLinkHandler()
    first = {
        "session_id": "session-1",
        "is_resolved": False,
        "match_confidence": 0.91,
        "match_details": {"method": "fingerprint"},
        "match_method": "fingerprint",
    }
    second = {
        "session_id": "session-2",
        "is_resolved": False,
        "match_confidence": 0.93,
        "match_details": {"method": "fingerprint"},
        "match_method": "fingerprint",
    }
    sessions = [first, second]
    claimed: list[str] = []

    monkeypatch.setattr(handler, "find_matching_session", lambda fingerprint: sessions.pop(0))

    def fake_mark_session_resolved(**kwargs):
        claimed.append(kwargs["session_id"])
        return kwargs["session_id"] == "session-2"

    monkeypatch.setattr(handler, "mark_session_resolved", fake_mark_session_resolved)

    resolved = handler.resolve_matching_session(fingerprint=object(), max_attempts=2)

    assert resolved == second
    assert claimed == ["session-1", "session-2"]


def test_resolve_matching_session_returns_exact_resolved_match(monkeypatch):
    handler = DeepLinkHandler()
    resolved_session = {
        "session_id": "resolved-1",
        "is_resolved": True,
        "match_confidence": 0.97,
        "match_details": {"method": "device_check"},
        "match_method": "device_check",
    }

    monkeypatch.setattr(handler, "find_matching_session", lambda fingerprint: resolved_session)

    def fail_mark_session_resolved(**kwargs):
        raise AssertionError("mark_session_resolved should not be called")

    monkeypatch.setattr(handler, "mark_session_resolved", fail_mark_session_resolved)

    resolved = handler.resolve_matching_session(fingerprint=object(), max_attempts=1)

    assert resolved == resolved_session
