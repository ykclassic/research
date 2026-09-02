from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user_or_github_actions
from app.api.analysis import quote_service
from app.main import app
from app.models import Quote, QuoteStatus
from app.models.market import Candle, OHLCVDataset, TechnicalAnalysisResult, Timeframe


SYMBOL = "BTC/USD"
SOURCE = "test_provider"
USER = {"id": "u1", "email": "user@example.com"}


def make_dataset(count: int = 260, *, incomplete_last: bool = False) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 100.0
    for index in range(count):
        price += 0.25
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=price - 0.1,
                high=price + 0.2,
                low=price - 0.2,
                close=price,
                volume=1000 + index,
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
        requested_at=datetime.now(timezone.utc),
        provider_timestamp=start + timedelta(hours=count - 1),
        candles=tuple(candles),
    )


def make_quote(price: float = 165.25) -> Quote:
    observed = datetime(2026, 8, 30, 5, 55, tzinfo=timezone.utc)
    return Quote(
        symbol=SYMBOL,
        provider_symbol="BTC/USD",
        price=price,
        currency="USD",
        timestamp=observed,
        provider_timestamp=observed,
        observed_at=observed,
        source="test_provider",
        status=QuoteStatus.LIVE,
        latency_ms=10,
        cache_hit=False,
    )


@pytest.fixture()
def authenticated_client(monkeypatch):
    app.dependency_overrides[get_current_user_or_github_actions] = lambda: USER

    async def fake_get_quote(symbol, force_refresh=False, excluded_providers=None):
        assert symbol == SYMBOL
        assert force_refresh is True
        assert excluded_providers is None
        return make_quote()

    monkeypatch.setattr(quote_service.provider, "get_quote", fake_get_quote)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user_or_github_actions, None)


def test_analysis_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/api/analysis/BTC%2FUSD")
    assert response.status_code == 401


def test_analysis_returns_canonical_feature_result(authenticated_client, monkeypatch):
    dataset = make_dataset()
    calls = {}

    async def fake_get_candles(symbol, timeframe, limit):
        calls.update(symbol=symbol, timeframe=timeframe, limit=limit)
        return dataset

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)

    response = authenticated_client.get(
        "/api/analysis/BTC%2FUSD",
        params={"timeframe": "1h", "limit": 250},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["symbol"] == SYMBOL
    assert body["timeframe"] == "1h"
    assert body["source"] == SOURCE
    assert body["candle_count"] == 260
    assert body["calculated_at"]
    assert body["latest_candle_timestamp"] == dataset.candles[-1].timestamp.isoformat().replace("+00:00", "Z")
    assert len(body["candles"]) == 260
    assert body["candles"][-1]["is_complete"] is True
    assert body["indicators"]["ema20"] is not None
    assert body["current_quote"]["symbol"] == SYMBOL
    assert body["current_quote"]["price"] == 165.25
    assert body["current_quote"]["status"] == "LIVE"
    assert body["current_quote"]["source"] == "test_provider"
    assert calls == {"symbol": SYMBOL, "timeframe": Timeframe.HOUR_1, "limit": 250}


def test_analysis_exposes_current_quote_separately_from_latest_completed_candle(authenticated_client, monkeypatch):
    dataset = make_dataset()

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    response = authenticated_client.get("/api/analysis/BTC%2FUSD")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "current_quote" in body
    assert "price" in body["current_quote"]
    assert body["latest_candle_timestamp"] == body["candles"][-1]["timestamp"]
    assert body["current_quote"]["timestamp"] != body["latest_candle_timestamp"]
    assert body["current_quote"]["price"] != body["candles"][-1]["close"]


def test_analysis_exposes_historical_indicator_panes(authenticated_client, monkeypatch):
    dataset = make_dataset()

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    response = authenticated_client.get("/api/analysis/BTC%2FUSD")

    assert response.status_code == 200, response.text
    panes = response.json()["indicator_panes"]
    assert {pane["id"] for pane in panes} == {"rsi14", "macd", "macd_signal", "macd_histogram"}
    for pane in panes:
        assert pane["title"]
        assert pane["unit"]
        timestamps = [point["timestamp"] for point in pane["points"]]
        assert timestamps == sorted(timestamps)
        assert len(timestamps) > 0

    rsi = next(pane for pane in panes if pane["id"] == "rsi14")
    assert rsi["min"] == 0.0
    assert rsi["max"] == 100.0


def test_analysis_excludes_forming_candle_from_feature_calculation(authenticated_client, monkeypatch):
    dataset = make_dataset(incomplete_last=True)

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)

    response = authenticated_client.get("/api/analysis/BTC%2FUSD")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["candles"]) == 260
    assert body["candles"][-1]["is_complete"] is False
    assert body["candle_count"] == 259
    assert body["latest_candle_timestamp"] == dataset.candles[-2].timestamp.isoformat().replace("+00:00", "Z")


def test_analysis_uses_serialized_candle_timestamp_not_stale_feature_metadata(authenticated_client, monkeypatch):
    dataset = make_dataset()
    stale_timestamp = dataset.candles[0].timestamp

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    def stale_feature_result(_dataset):
        return TechnicalAnalysisResult(
            symbol=SYMBOL,
            timeframe=Timeframe.HOUR_1,
            source=SOURCE,
            calculated_at=datetime.now(timezone.utc),
            latest_candle_timestamp=stale_timestamp,
            candle_count=1,
            indicators={"ema20": 1.0},
        )

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    monkeypatch.setattr("app.api.analysis.calculate_feature_set", stale_feature_result)

    response = authenticated_client.get("/api/analysis/BTC%2FUSD")

    assert response.status_code == 200, response.text
    body = response.json()
    expected = dataset.candles[-1].timestamp.isoformat().replace("+00:00", "Z")
    assert body["latest_candle_timestamp"] == expected
    assert body["candle_count"] == len(dataset.candles)


def test_analysis_rejects_invalid_timeframe(authenticated_client):
    response = authenticated_client.get(
        "/api/analysis/BTC%2FUSD",
        params={"timeframe": "2h"},
    )
    assert response.status_code == 422


def test_analysis_rejects_invalid_limit(authenticated_client):
    response = authenticated_client.get(
        "/api/analysis/BTC%2FUSD",
        params={"limit": 49},
    )
    assert response.status_code == 422


def test_analysis_maps_provider_failure_to_503(authenticated_client, monkeypatch):
    async def failing_get_candles(symbol, timeframe, limit):
        raise ValueError("provider returned malformed candle data")

    monkeypatch.setattr(quote_service.provider, "get_candles", failing_get_candles)

    response = authenticated_client.get("/api/analysis/BTC%2FUSD")

    assert response.status_code == 503
    assert response.json()["detail"] == "provider returned malformed candle data"


def test_analysis_maps_feature_failure_to_503(authenticated_client, monkeypatch):
    dataset = make_dataset()

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    def failing_feature_engine(dataset):
        raise ValueError("feature calculation failed")

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    monkeypatch.setattr("app.api.analysis.calculate_feature_set", failing_feature_engine)

    response = authenticated_client.get("/api/analysis/BTC%2FUSD")

    assert response.status_code == 503
    assert response.json()["detail"] == "feature calculation failed"
