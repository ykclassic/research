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
    provider_timestamp = datetime(2026, 8, 30, 8, 40, tzinfo=timezone.utc)

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
    provider_timestamp = datetime(2026, 8, 30, 8, 41, tzinfo=timezone.utc)

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
