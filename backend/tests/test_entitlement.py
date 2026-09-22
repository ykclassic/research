from unittest.mock import Mock

import pytest

from app.services import entitlement


def test_require_feature_allows_enabled_feature(monkeypatch):
    monkeypatch.setattr(
        entitlement,
        "get_entitlement_snapshot",
        lambda *_: {
            "plan_id": "pro",
            "features": {"backtesting": True},
            "plan": {"id": "pro"},
            "limits": {},
            "subscription": None,
        },
    )
    result = entitlement.require_feature("token", "user", "backtesting")
    assert result["plan_id"] == "pro"


def test_require_feature_rejects_disabled_feature(monkeypatch):
    monkeypatch.setattr(
        entitlement,
        "get_entitlement_snapshot",
        lambda *_: {
            "plan_id": "free",
            "features": {},
            "plan": {"id": "free"},
            "limits": {},
            "subscription": None,
        },
    )
    with pytest.raises(entitlement.FeatureNotEntitledError):
        entitlement.require_feature("token", "user", "backtesting")


def test_consume_usage_returns_atomic_result(monkeypatch):
    response = Mock()
    response.json.return_value = [{
        "allowed": True,
        "used": 4,
        "limit_value": 5,
        "period_start": "2026-09-01",
        "plan_id": "free",
    }]
    monkeypatch.setattr(entitlement, "_request", lambda *args, **kwargs: response)
    result = entitlement.consume_usage("token", "user", "ai_research_runs")
    assert result["allowed"] is True
    assert result["used"] == 4


def test_consume_usage_raises_on_hard_limit(monkeypatch):
    response = Mock()
    response.json.return_value = [{
        "allowed": False,
        "used": 5,
        "limit_value": 5,
        "period_start": "2026-09-01",
        "plan_id": "free",
    }]
    monkeypatch.setattr(entitlement, "_request", lambda *args, **kwargs: response)
    with pytest.raises(entitlement.UsageLimitExceededError):
        entitlement.consume_usage("token", "user", "ai_research_runs")


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError):
        entitlement.consume_usage("token", "user", "unknown_metric")


def test_get_usage_loads_threshold_notifications(monkeypatch):
    snapshot = {
        "plan_id": "free",
        "plan": {"id": "free"},
        "features": {},
        "limits": {
            "ai_research_runs": {"limit": 5, "reset_period": "monthly"},
        },
        "subscription": None,
    }
    response = Mock()
    response.json.side_effect = [
        [{"metric": "ai_research_runs", "period_start": "2026-09-01", "used": 2, "updated_at": "2026-09-01T00:00:00Z"}],
        [{"metric": "ai_research_runs", "threshold_percent": 80, "used": 4, "limit_value": 5, "created_at": "2026-09-10T00:00:00Z"}],
    ]

    def request(method, path, *args, **kwargs):
        if path == "usage_counters":
            return response
        if path == "billing_usage_notifications":
            return response
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(entitlement, "get_entitlement_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(entitlement, "_request", request)
    result = entitlement.get_usage("token", "user")

    assert result["notifications"][0]["threshold_percent"] == 80
    assert result["metrics"]["ai_research_runs"]["used"] == 2
