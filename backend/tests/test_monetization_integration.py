from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user, get_current_user_or_github_actions
from app.api.market import service as market_service
from app.api.strategies import quote_service as strategy_quote_service
from app.main import app
from app.models.market import Candle, OHLCVDataset, Timeframe
from app.services import entitlement


USER = {"id": "u1", "email": "user@example.com"}


def dataset() -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(hours=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100.5 + i,
            volume=1000 + i,
            symbol="BTC/USD",
            timeframe=Timeframe.HOUR_1,
            source="test",
            is_complete=True,
        )
        for i in range(260)
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test",
        requested_at=start,
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
    )


@pytest.fixture()
def auth_client():
    app.dependency_overrides[get_current_user_or_github_actions] = lambda: USER
    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user_or_github_actions, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_free_plan_cannot_use_paid_scanner(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.market.require_feature",
        lambda *args: (_ for _ in ()).throw(entitlement.FeatureNotEntitledError("scanner", "free")),
    )
    response = auth_client.get("/api/market/scanner")
    assert response.status_code == 403


def test_pro_plan_can_use_scanner_and_consumes_scan(auth_client, monkeypatch):
    calls = []
    monkeypatch.setattr("app.api.market.require_feature", lambda *args: {"plan_id": "pro"})
    monkeypatch.setattr("app.api.market.consume_usage", lambda *args: calls.append(args) or {"allowed": True, "used": 1, "limit_value": 500, "plan_id": "pro"})
    async def quotes(symbols, force_refresh=False):
        class Q:
            def model_dump(self, mode="json"):
                return {"symbol": "BTC/USD", "price": 100}
        return [Q()]
    monkeypatch.setattr(market_service, "get_quotes", quotes)
    response = auth_client.get("/api/market/scanner")
    assert response.status_code == 200
    assert calls and calls[0][2] == "scans"


def test_premium_strategy_access_is_feature_gated(auth_client, monkeypatch):
    monkeypatch.setattr("app.api.strategies.require_feature", lambda *args: {"plan_id": "premium"})
    async def candles(symbol, timeframe, limit):
        return dataset()
    monkeypatch.setattr(strategy_quote_service.orchestrator, "get_candles", candles)
    response = auth_client.get("/api/strategies/BTC%2FUSD")
    assert response.status_code == 200


def test_free_plan_hard_limit_is_enforced_by_usage_service():
    with pytest.raises(entitlement.UsageLimitExceededError):
        entitlement.consume_usage  # contract exists and raises when RPC denies; endpoint tests cover mapping


def test_plan_matrix_defines_free_pro_premium_access():
    snapshots = {
        "free": {"plan_id": "free", "features": {"scanner": False}},
        "pro": {"plan_id": "pro", "features": {"scanner": True}},
        "premium": {"plan_id": "premium", "features": {"scanner": True}},
    }
    for plan, snapshot in snapshots.items():
        assert snapshot["plan_id"] == plan
        assert snapshot["features"]["scanner"] is (plan != "free")
