from __future__ import annotations

from datetime import datetime, timezone

from app.services import privacy_data


def test_history_csv_is_structured_and_includes_payload() -> None:
    original = privacy_data.get_all_history_for_export
    try:
        privacy_data.get_all_history_for_export = lambda _token, _user: [{
            "id": "1",
            "record_type": "REPORT",
            "symbol": "BTC/USD",
            "query": None,
            "title": "BTC Market Research",
            "saved": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"confidence": 0.91},
        }]
        content = privacy_data.history_csv("token", "user")
    finally:
        privacy_data.get_all_history_for_export = original

    text = content.decode("utf-8-sig")
    assert "record_type" in text
    assert "REPORT" in text
    assert "BTC/USD" in text
    assert "confidence" in text


def test_retention_forever_does_not_delete(monkeypatch) -> None:
    called = False

    def fake_request(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("retention must not query the database for Forever")

    monkeypatch.setattr(privacy_data, "_request", fake_request)
    assert privacy_data.apply_retention("token", "user", 0) == 0
    assert called is False


def test_retention_deletes_only_expired_unsaved_records(monkeypatch) -> None:
    captured = {}

    class Response:
        def json(self):
            return [{"id": "expired"}]

    def fake_request(method, path, access_token, **kwargs):
        captured.update({"method": method, "path": path, "access_token": access_token, **kwargs})
        return Response()

    monkeypatch.setattr(privacy_data, "_request", fake_request)
    assert privacy_data.apply_retention("token", "user", 30) == 1
    assert captured["method"] == "DELETE"
    assert captured["path"] == "research_history"
    assert captured["params"]["saved"] == "eq.false"
    assert captured["params"]["user_id"] == "eq.user"
