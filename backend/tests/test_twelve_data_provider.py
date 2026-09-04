from datetime import datetime, timezone

import pytest

from app.config import settings
from app.providers.twelve_data import TwelveDataProvider


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    def __init__(self, *, payload: dict, calls: list[dict], **_kwargs):
        self.payload = payload
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, *, params: dict):
        self.calls.append({"url": url, "params": params})
        return FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_get_quote_requests_one_minute_interval_and_preserves_provider_timestamp(monkeypatch):
    provider = TwelveDataProvider()
    calls: list[dict] = []
    provider_timestamp = datetime.now(timezone.utc).replace(microsecond=0)

    payload = {
        "symbol": "BTC/USD",
        "close": "114250.50",
        "last_update_at": provider_timestamp.isoformat(),
    }

    monkeypatch.setattr(
        "app.providers.twelve_data.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(payload=payload, calls=calls, **kwargs),
    )
    monkeypatch.setattr(settings, "twelve_data_api_key", "test-key")
    monkeypatch.setattr(settings, "http_max_retries", 0)

    quote = await provider.get_quote("BTC/USD")

    assert quote.status.value == "LIVE"
    assert quote.price == 114250.50
    assert quote.provider_timestamp == provider_timestamp
    assert quote.timestamp == provider_timestamp
    assert quote.observed_at is not None
    assert calls == [
        {
            "url": "https://api.twelvedata.com/quote",
            "params": {
                "symbol": "BTC/USD",
                "interval": "1min",
                "apikey": "test-key",
            },
        }
    ]


@pytest.mark.asyncio
async def test_get_quote_accepts_twelve_data_timestamp_when_last_update_at_is_absent(monkeypatch):
    provider = TwelveDataProvider()
    calls: list[dict] = []
    provider_timestamp = datetime.now(timezone.utc).replace(microsecond=0)

    payload = {
        "symbol": "BTC/USD",
        "close": "114251.00",
        "timestamp": int(provider_timestamp.timestamp()),
    }

    monkeypatch.setattr(
        "app.providers.twelve_data.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(payload=payload, calls=calls, **kwargs),
    )
    monkeypatch.setattr(settings, "twelve_data_api_key", "test-key")
    monkeypatch.setattr(settings, "http_max_retries", 0)

    quote = await provider.get_quote("BTC/USD")

    assert quote.provider_timestamp == provider_timestamp
    assert quote.timestamp == provider_timestamp
    assert quote.price == 114251.00


@pytest.mark.asyncio
async def test_get_candles_uses_server_side_start_and_end_without_outputsize(monkeypatch):
    provider = TwelveDataProvider()
    calls: list[dict] = []
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 1, 3, tzinfo=timezone.utc)
    payload = {
        "values": [
            {
                "datetime": "2026-08-01 03:00:00",
                "open": "103",
                "high": "104",
                "low": "102",
                "close": "103.5",
                "volume": "1003",
            },
            {
                "datetime": "2026-08-01 02:00:00",
                "open": "102",
                "high": "103",
                "low": "101",
                "close": "102.5",
                "volume": "1002",
            },
            {
                "datetime": "2026-08-01 01:00:00",
                "open": "101",
                "high": "102",
                "low": "100",
                "close": "101.5",
                "volume": "1001",
            },
            {
                "datetime": "2026-08-01 00:00:00",
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100.5",
                "volume": "1000",
            },
        ]
    }

    monkeypatch.setattr(
        "app.providers.twelve_data.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(payload=payload, calls=calls, **kwargs),
    )
    monkeypatch.setattr(settings, "twelve_data_api_key", "test-key")
    monkeypatch.setattr(settings, "http_max_retries", 0)

    dataset = await provider.get_candles(
        "BTC/USD",
        "1h",
        start_date=start,
        end_date=end,
    )

    assert len(dataset.candles) == 4
    assert calls == [
        {
            "url": "https://api.twelvedata.com/time_series",
            "params": {
                "symbol": "BTC/USD",
                "interval": "1h",
                "apikey": "test-key",
                "timezone": "UTC",
                "start_date": "2026-08-01 00:00:00",
                "end_date": "2026-08-01 03:00:00",
            },
        }
    ]


@pytest.mark.asyncio
async def test_get_candles_rejects_partial_or_reverse_range(monkeypatch):
    provider = TwelveDataProvider()
    with pytest.raises(ValueError, match="require both"):
        await provider.get_candles("BTC/USD", "1h", start_date=datetime.now(timezone.utc))

    with pytest.raises(ValueError, match="before end"):
        await provider.get_candles(
            "BTC/USD",
            "1h",
            start_date=datetime(2026, 8, 2, tzinfo=timezone.utc),
            end_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
