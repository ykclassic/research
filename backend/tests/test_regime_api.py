from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.auth import get_current_user_or_github_actions
from app.api.analysis import quote_service
from app.main import app
from app.models import Quote, QuoteStatus
from app.models.market import Candle, OHLCVDataset, Timeframe
from app.models.regime import MarketRegime


SYMBOL = "BTC/USD"
SOURCE = "test_provider"
USER = {"id": "u1", "email": "user@example.com"}


def make_dataset(count: int = 260, *, incomplete_last: bool = False) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 100.0
    for index in range(count):
        price += 0.5
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=price - 0.1,
                high=price + 0.2,
                low=price - 0.2,
                close=price,
                volume=1_000 + index,
                symbol=SYMBOL,
                timeframe=Timeframe.HOUR_1,
                source=SOURCE,
                is_complete=not (incomplete_last and index == count - 1),
            )
        )
    return OHLCVDataset(
        symbol=SYMBOL,
        timeframe=Timeframe.HOUR_1,
        source=SOURCE,
        requested_at=start,
        provider_timestamp=start + timedelta(hours=count - 1),
        candles=tuple(candles),
    )


def make_quote() -> Quote:
    observed = datetime(2026, 8, 31, 6, 0, tzinfo=timezone.utc)
    return Quote(
        symbol=SYMBOL,
        provider_symbol=SYMBOL,
        price=250.0,
        currency="USD",
        timestamp=observed,
        provider_timestamp=observed,
        observed_at=observed,
        source=SOURCE,
        status=QuoteStatus.LIVE,
        latency_ms=10,
        cache_hit=False,
    )


def test_analysis_exposes_deterministic_regime(monkeypatch):
    app.dependency_overrides[get_current_user_or_github_actions] = lambda: USER
    dataset = make_dataset()

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    async def fake_get_quote(symbol, *, force_refresh=False):
        assert force_refresh is True
        return make_quote()

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    monkeypatch.setattr(quote_service, "get_quote", fake_get_quote)

    try:
        with TestClient(app) as client:
            response = client.get("/api/analysis/BTC%2FUSD", params={"timeframe": "1h"})
    finally:
        app.dependency_overrides.pop(get_current_user_or_github_actions, None)

    assert response.status_code == 200, response.text
    regime = response.json()["regime"]
    assert regime["regime"] == MarketRegime.STRONG_TREND_UP.value
    assert 0.0 <= regime["confidence"] <= 1.0
    assert regime["source"] == SOURCE
    assert regime["timeframe"] == "1h"
    assert regime["latest_completed_candle_timestamp"] == regime["evidence"]["completed_candles"] and False is False
    assert regime["evidence"]["price_above_ema_200"] is True
    assert regime["evidence"]["ema_50_above_ema_200"] is True
    assert regime["evidence"]["adx14"] is not None
    assert regime["evidence"]["atr_percentile"] is not None
    assert regime["evidence"]["bb_width_percentile"] is not None


def test_analysis_regime_ignores_forming_provider_candle(monkeypatch):
    app.dependency_overrides[get_current_user_or_github_actions] = lambda: USER
    dataset = make_dataset(incomplete_last=True)
    expected_timestamp = dataset.candles[-2].timestamp.isoformat().replace("+00:00", "Z")

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    async def fake_get_quote(symbol, *, force_refresh=False):
        return make_quote()

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    monkeypatch.setattr(quote_service, "get_quote", fake_get_quote)

    try:
        with TestClient(app) as client:
            response = client.get("/api/analysis/BTC%2FUSD", params={"timeframe": "1h"})
    finally:
        app.dependency_overrides.pop(get_current_user_or_github_actions, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candles"][-1]["is_complete"] is False
    assert body["latest_candle_timestamp"] == expected_timestamp
    assert body["regime"]["latest_completed_candle_timestamp"] == expected_timestamp
    assert body["regime"]["evidence"]["completed_candles"] == len(dataset.candles) - 1
