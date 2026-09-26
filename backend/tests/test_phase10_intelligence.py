import pytest

from app.services import phase10_intelligence as service


def test_chart_event_type_is_strict(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported chart event type"):
        service.create_chart_event("user", {"symbol": "BTC/USD", "event_type": "UNKNOWN"})


def test_fundamental_type_is_strict(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported fundamental observation type"):
        service.create_fundamental_observation("user", {"symbol": "AAPL", "observation_type": "GUESS"})


def test_model_evaluation_requires_sufficient_evidence(monkeypatch):
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))

        class Response:
            def json(self):
                return [{"id": "v1", "status": "VALIDATING", "test_passed": False}]

        return Response()

    monkeypatch.setattr(service, "service_request", fake_request)
    result = service.evaluate_model_version(
        "user",
        "v1",
        {"sample_size": 99},
        {"error": 0.1},
        {"TREND": {"sample_size": 99}},
        {"status": "STABLE"},
    )
    assert result["test_passed"] is False


def test_model_promotion_requires_explicit_validation(monkeypatch):
    def fake_one(path, params):
        if path == "research_model_versions":
            return {"id": "v1", "model_id": "m1", "test_passed": False}
        return {"id": "m1", "active_version_id": None}

    monkeypatch.setattr(service, "_one", fake_one)
    with pytest.raises(ValueError, match="cannot be promoted"):
        service.promote_model_version("user", "v1")


def test_model_types_are_governed(monkeypatch):
    monkeypatch.setattr(service, "service_request", lambda *args, **kwargs: type("Response", (), {"json": lambda self: [{"id": "m1"}]})())
    with pytest.raises(ValueError, match="Unsupported model type"):
        service.create_model("user", {"name": "candidate", "model_type": "AUTONOMOUS_TRADER"})
