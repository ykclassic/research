from app.services import research_history


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_create_history_record_persists_auditable_payload(monkeypatch):
    calls = []

    def fake_request(method, path, access_token, **kwargs):
        calls.append((method, path, access_token, kwargs))
        return FakeResponse([{"id": "history-1", "record_type": "REPORT", "symbol": "BTC/USD", "payload": {"score": 76}}])

    monkeypatch.setattr(research_history, "_request", fake_request)
    result = research_history.create_history_record(
        "token",
        "user-1",
        record_type="REPORT",
        symbol="BTC/USD",
        title="BTC/USD Market Research",
        payload={"score": 76},
    )

    assert result["id"] == "history-1"
    assert calls[0][0:3] == ("POST", "research_history", "token")
    assert calls[0][3]["json"]["user_id"] == "user-1"
    assert calls[0][3]["json"]["payload"] == {"score": 76}


def test_history_filters_are_user_scoped(monkeypatch):
    calls = []

    def fake_request(method, path, access_token, **kwargs):
        calls.append(kwargs["params"])
        return FakeResponse([])

    monkeypatch.setattr(research_history, "_request", fake_request)
    result = research_history.list_history("token", "user-1", record_type="REPORT", symbol="BTC/USD", saved=True, limit=20)

    assert result == []
    params = calls[0]
    assert params["user_id"] == "eq.user-1"
    assert params["record_type"] == "eq.REPORT"
    assert params["symbol"] == "eq.BTC/USD"
    assert params["saved"] == "eq.true"
    assert params["limit"] == "20"
