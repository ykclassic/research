from unittest.mock import Mock

import pytest

from app.services import entitlement


def test_require_feature_allows_advanced_research(monkeypatch):
    monkeypatch.setattr(
        entitlement,
        "get_entitlement_snapshot",
        lambda *_: {
            "plan_id": "pro",
            "features": {"advanced_research": True},
            "plan": {"id": "pro"},
            "limits": {},
            "subscription": None,
        },
    )
    result = entitlement.require_feature("token", "user", "advanced_research")
    assert result["plan_id"] == "pro"


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


def test_expired_paid_subscription_resolves_to_free(monkeypatch):
    subscription = {
        "id": "sub-expired",
        "plan_id": "premium",
        "status": "active",
        "current_period_end": "2026-10-01T00:00:00+00:00",
        "trial_ends_at": None,
    }
    free_plan = {
        "id": "free",
        "name": "Free",
        "description": "",
        "monthly_price_minor": 0,
        "currency": "USD",
        "display_order": 10,
        "active": True,
    }
    premium_plan = {**free_plan, "id": "premium", "name": "Premium / Professional"}
    response = Mock()
    response.json.side_effect = [
        [subscription],
        [premium_plan, free_plan],
        [],
        [],
    ]

    monkeypatch.setattr(entitlement, "_request", lambda *args, **kwargs: response)

    snapshot = entitlement.get_entitlement_snapshot("token", "user")

    assert snapshot["plan_id"] == "free"
    assert snapshot["plan"]["id"] == "free"


@pytest.mark.parametrize("feature", ["copilot_deep_research", "copilot_multi_step"])
def test_research_copilot_features_are_registered(monkeypatch, feature):
    monkeypatch.setattr(
        entitlement,
        "get_entitlement_snapshot",
        lambda *_: {
            "plan_id": "pro",
            "features": {feature: True},
            "plan": {"id": "pro"},
            "limits": {},
            "subscription": None,
        },
    )

    result = entitlement.require_feature("token", "user", feature)

    assert result["plan_id"] == "pro"


def test_research_copilot_usage_metric_is_registered(monkeypatch):
    response = Mock()
    response.json.return_value = [{
        "allowed": True,
        "used": 1,
        "limit_value": 100,
        "period_start": "2026-10-01",
        "plan_id": "pro",
    }]
    monkeypatch.setattr(entitlement, "_request", lambda *args, **kwargs: response)

    result = entitlement.consume_usage("token", "user", "copilot_research_runs")

    assert result["allowed"] is True


def test_billing_plan_catalog_returns_complete_fail_closed_matrix(monkeypatch):
    plans = [
        {"id": "free", "name": "Free"},
        {"id": "pro", "name": "Pro"},
        {"id": "premium", "name": "Premium / Professional"},
    ]
    features = [
        {"id": "backtesting"},
        {"id": "webhooks"},
        {"id": "copilot_deep_research"},
        {"id": "copilot_multi_step"},
        {"id": "live_trade_execution"},
    ]
    rows = [
        {"plan_id": "free", "feature_id": "backtesting", "enabled": False},
        {"plan_id": "pro", "feature_id": "backtesting", "enabled": True},
        {"plan_id": "pro", "feature_id": "copilot_deep_research", "enabled": True},
        {"plan_id": "pro", "feature_id": "copilot_multi_step", "enabled": False},
        {"plan_id": "pro", "feature_id": "webhooks", "enabled": False},
        {"plan_id": "premium", "feature_id": "backtesting", "enabled": True},
        {"plan_id": "premium", "feature_id": "copilot_deep_research", "enabled": True},
        {"plan_id": "premium", "feature_id": "copilot_multi_step", "enabled": True},
        {"plan_id": "premium", "feature_id": "webhooks", "enabled": True},
        {"plan_id": "premium", "feature_id": "live_trade_execution", "enabled": True},
    ]
    payloads = {
        "billing_plans": plans,
        "billing_features": features,
        "billing_plan_features": rows,
    }

    def request(method, path, *args, **kwargs):
        response = Mock()
        response.json.return_value = payloads[path]
        return response

    monkeypatch.setattr(entitlement, "_request", request)
    catalog = entitlement.get_billing_plan_catalog("token")
    by_plan = {plan["id"]: plan for plan in catalog}

    assert by_plan["pro"]["features"] == {
        "backtesting": True,
        "webhooks": False,
        "copilot_deep_research": True,
        "copilot_multi_step": False,
        "live_trade_execution": False,
    }
    assert by_plan["premium"]["features"]["copilot_multi_step"] is True
    assert by_plan["premium"]["features"]["live_trade_execution"] is True
    assert by_plan["free"]["features"]["backtesting"] is False


def test_phase10_entitlement_is_registered():
    assert "phase10_intelligence" in entitlement.FEATURE_KEYS


def test_pro_cannot_resolve_premium_only_entitlements(monkeypatch):
    for feature in ("webhooks", "api", "mcp", "team_workspaces", "copilot_multi_step", "live_trade_execution"):
        monkeypatch.setattr(
            entitlement,
            "get_entitlement_snapshot",
            lambda *_: {
                "plan_id": "pro",
                "features": {feature: False},
                "plan": {"id": "pro"},
                "limits": {},
                "subscription": None,
            },
        )
        with pytest.raises(entitlement.FeatureNotEntitledError):
            entitlement.require_feature("token", "user", feature)
