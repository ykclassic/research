from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.supabase_data import DataRequestError, _request


FEATURE_KEYS = {
    "core_research", "watchlists", "basic_portfolio", "signal_intelligence",
    "ai_research", "advanced_portfolio_analytics", "backtesting",
    "strategy_builder", "scanner", "webhooks", "scheduled_workflows",
    "api", "mcp", "exports", "team_workspaces",
}

METRICS = {
    "ai_research_runs", "scans", "exports", "api_requests",
    "historical_queries", "scheduled_workflows",
}


class EntitlementError(Exception):
    pass


class FeatureNotEntitledError(EntitlementError):
    def __init__(self, feature: str, plan_id: str) -> None:
        super().__init__(f"Feature '{feature}' is not available on the {plan_id} plan.")
        self.feature = feature
        self.plan_id = plan_id


class UsageLimitExceededError(EntitlementError):
    def __init__(self, metric: str, used: int, limit: int, plan_id: str) -> None:
        super().__init__(f"Monthly {metric.replace('_', ' ')} limit reached ({used}/{limit}).")
        self.metric = metric
        self.used = used
        self.limit = limit
        self.plan_id = plan_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_entitlement_snapshot(access_token: str, user_id: str) -> dict[str, Any]:
    subscriptions = _request(
        "GET", "billing_subscriptions", access_token,
        params={"select": "*", "user_id": f"eq.{user_id}", "order": "updated_at.desc", "limit": "1"},
    ).json()
    subscription = subscriptions[0] if subscriptions else None
    plan_id = "free"
    if subscription and subscription.get("status") in {"trialing", "active", "past_due", "unpaid", "paused"}:
        trial_ends = subscription.get("trial_ends_at")
        if not trial_ends or trial_ends > _now_iso():
            plan_id = subscription.get("plan_id") or "free"

    plans = _request(
        "GET", "billing_plans", access_token,
        params={"select":"id,name,description,monthly_price_minor,currency,display_order,active", "active":"eq.true", "order":"display_order.asc"},
    ).json()
    plan = next((item for item in plans if item["id"] == plan_id), next(item for item in plans if item["id"] == "free"))

    feature_rows = _request(
        "GET", "billing_plan_features", access_token,
        params={"select":"feature_id,enabled", "plan_id": f"eq.{plan['id']}", "enabled":"eq.true"},
    ).json()
    limit_rows = _request(
        "GET", "billing_plan_limits", access_token,
        params={"select":"metric,limit_value,reset_period", "plan_id": f"eq.{plan['id']}"},
    ).json()
    features = {row["feature_id"]: True for row in feature_rows}
    limits = {row["metric"]: {"limit": row["limit_value"], "reset_period": row["reset_period"]} for row in limit_rows}

    return {"plan": plan, "plan_id": plan["id"], "features": features, "limits": limits, "subscription": subscription}


def require_feature(access_token: str, user_id: str, feature: str) -> dict[str, Any]:
    if feature not in FEATURE_KEYS:
        raise ValueError(f"Unknown entitlement feature: {feature}")
    snapshot = get_entitlement_snapshot(access_token, user_id)
    if not snapshot["features"].get(feature, False):
        raise FeatureNotEntitledError(feature, snapshot["plan_id"])
    return snapshot


def consume_usage(access_token: str, user_id: str, metric: str, quantity: int = 1) -> dict[str, Any]:
    if metric not in METRICS:
        raise ValueError(f"Unknown usage metric: {metric}")
    response = _request(
        "POST", "rpc/consume_usage", access_token,
        json={"p_user_id": user_id, "p_metric": metric, "p_quantity": quantity},
    )
    rows = response.json()
    if not rows:
        raise DataRequestError("Usage metering returned no result.")
    result = rows[0]
    if not result.get("allowed"):
        raise UsageLimitExceededError(metric, int(result.get("used", 0)), int(result.get("limit_value", 0)), result.get("plan_id", "free"))
    return result


def get_usage(access_token: str, user_id: str) -> dict[str, Any]:
    snapshot = get_entitlement_snapshot(access_token, user_id)
    rows = _request(
        "GET", "usage_counters", access_token,
        params={"select":"metric,period_start,used,updated_at", "user_id": f"eq.{user_id}", "period_start": f"eq.{datetime.now(timezone.utc).date().replace(day=1).isoformat()}"},
    ).json()
    used = {row["metric"]: row for row in rows}
    return {
        "period_start": datetime.now(timezone.utc).date().replace(day=1).isoformat(),
        "plan_id": snapshot["plan_id"],
        "notifications": notifications,\n        "metrics": {
            metric: {
                "used": int(used.get(metric, {}).get("used", 0)),
                "limit": int(config["limit"]),
                "reset_period": config["reset_period"],
                "remaining": None if int(config["limit"]) == -1 else max(int(config["limit"]) - int(used.get(metric, {}).get("used", 0)), 0),
            }
            for metric, config in snapshot["limits"].items()
        },
    }


def start_pro_trial(access_token: str, user_id: str, days: int = 14) -> dict[str, Any]:
    response = _request(
        "POST", "rpc/start_pro_trial", access_token,
        json={"p_user_id": user_id, "p_days": days},
    )
    rows = response.json()
    if not rows:
        raise DataRequestError("Trial could not be started.")
    return rows[0]
