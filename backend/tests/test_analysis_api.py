from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.api.analysis import quote_service
from app.main import app
from app.models.market import Candle, OHLCVDataset, Timeframe


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


@pytest.fixture()
def authenticated_client():
    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


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
    assert calls == {"symbol": SYMBOL, "timeframe": Timeframe.HOUR_1, "limit": 250}


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
