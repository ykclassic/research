from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.auth import get_current_user_or_github_actions
from app.api.analysis import quote_service
from app.main import app
from app.models.market import Candle, OHLCVDataset, Timeframe


USER = {"id": "u1", "email": "user@example.com"}


def make_dataset() -> OHLCVDataset:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(hours=index),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100.5 + index,
            volume=1000 + index,
            symbol="BTC/USD",
            timeframe=Timeframe.HOUR_1,
            source="test_provider",
            is_complete=True,
        )
        for index in range(25)
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test_provider",
        requested_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        candles=candles,
    )


def test_analysis_forwards_server_range_without_client_side_filtering(monkeypatch):
    app.dependency_overrides[get_current_user_or_github_actions] = lambda: USER
    calls = {}

    async def fake_get_candles(symbol, timeframe, limit, start_date=None, end_date=None):
        calls.update(symbol=symbol, timeframe=timeframe, limit=limit, start_date=start_date, end_date=end_date)
        return make_dataset()

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/analysis/BTC%2FUSD",
                params={
                    "timeframe": "1h",
                    "start": "2026-08-01T00:00:00Z",
                    "end": "2026-08-03T23:59:59Z",
                },
            )
        assert response.status_code == 200, response.text
        assert calls["symbol"] == "BTC/USD"
        assert calls["timeframe"] == Timeframe.HOUR_1
        assert calls["start_date"] == datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert calls["end_date"] == datetime(2026, 8, 3, 23, 59, 59, tzinfo=timezone.utc)
        assert len(response.json()["candles"]) == 25
    finally:
        app.dependency_overrides.pop(get_current_user_or_github_actions, None)


def test_analysis_rejects_partial_historical_range():
    app.dependency_overrides[get_current_user_or_github_actions] = lambda: USER
    try:
        with TestClient(app) as client:
            response = client.get("/api/analysis/BTC%2FUSD", params={"start": "2026-08-01T00:00:00Z"})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user_or_github_actions, None)
