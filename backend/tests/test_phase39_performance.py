import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.analysis import quote_service
from app.api.auth import get_current_user
from app.config import settings
from app.main import app
from app.models.market import Candle, OHLCVDataset, Timeframe


USER = {"id": "u1", "email": "user@example.com"}


def make_dataset(count: int = 250) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(hours=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0 + index,
            symbol="BTC/USD",
            timeframe=Timeframe.HOUR_1,
            source="test_provider",
            is_complete=True,
        )
        for index in range(count)
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test_provider",
        requested_at=start,
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
    )


def test_health_exposes_server_timing():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["server-timing"].startswith("app;dur=")


def test_analysis_provider_timeout_is_bounded(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: USER
    original_timeout = settings.analysis_timeout_seconds
    settings.analysis_timeout_seconds = 0.01

    async def slow_get_candles(symbol, timeframe, limit):
        await asyncio.sleep(0.05)
        return make_dataset()

    monkeypatch.setattr(quote_service.provider, "get_candles", slow_get_candles)
    try:
        with TestClient(app) as client:
            response = client.get("/api/analysis/BTC%2FUSD")
    finally:
        settings.analysis_timeout_seconds = original_timeout
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Market-data provider exceeded the analysis latency budget."


def test_analysis_server_timing_is_present(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: USER

    async def fast_get_candles(symbol, timeframe, limit):
        return make_dataset()

    monkeypatch.setattr(quote_service.provider, "get_candles", fast_get_candles)
    try:
        with TestClient(app) as client:
            response = client.get("/api/analysis/BTC%2FUSD", params={"limit": 250})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.headers["server-timing"].startswith("app;dur=")
    assert response.headers["cache-control"] == "no-store"


def test_analysis_response_remains_numerically_deterministic(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: USER

    async def fast_get_candles(symbol, timeframe, limit):
        return make_dataset()

    monkeypatch.setattr(quote_service.provider, "get_candles", fast_get_candles)
    try:
        with TestClient(app) as client:
            first = client.get("/api/analysis/BTC%2FUSD", params={"limit": 250}).json()
            second = client.get("/api/analysis/BTC%2FUSD", params={"limit": 250}).json()
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert first["indicators"] == second["indicators"]
    assert first["latest_candle_timestamp"] == second["latest_candle_timestamp"]
    assert first["candle_count"] == second["candle_count"]
