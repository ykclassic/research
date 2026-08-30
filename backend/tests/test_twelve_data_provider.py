from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import QuoteStatus
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


def install_fake_client(monkeypatch, payload: dict, calls: list[dict]) -> None:
    monkeypatch.setattr(
        "app.providers.twelve_data.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(payload=payload, calls=calls, **kwargs),
    )
    monkeypatch.setattr(settings, "twelve_data_api_key", "test-key")
    monkeypatch.setattr(settings, "http_max_retries", 0)


@pytest.mark.asyncio
async def test_get_quote_requests_one_minute_interval_and_preserves_provider_timestamp(monkeypatch):
    provider = TwelveDataProvider()
    calls: list[dict] = []
    provider_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)

    payload = {
        "symbol": "BTC/USD",
        "close": "114250.50",
        "last_update_at": provider_timestamp.isoformat(),
    }
    install_fake_client(monkeypatch, payload, calls)

    quote = await provider.get_quote("BTC/USD")

    assert quote.status == QuoteStatus.LIVE
    assert quote.price == 114250.50
    assert quote.provider_timestamp == provider_timestamp
    assert quote.timestamp == provider_timestamp
    assert quote.observed_at is not None
    assert quote.error is None
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
    provider_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)

    payload = {
        "symbol": "BTC/USD",
        "close": "114251.00",
        "timestamp": int(provider_timestamp.timestamp()),
    }
    install_fake_client(monkeypatch, payload, calls)

    quote = await provider.get_quote("BTC/USD")

    assert quote.status == QuoteStatus.LIVE
    assert quote.provider_timestamp == datetime.fromtimestamp(
        int(provider_timestamp.timestamp()),
        tz=timezone.utc,
    )
    assert quote.timestamp == quote.provider_timestamp
    assert quote.price == 114251.00


@pytest.mark.asyncio
async def test_get_quote_marks_provider_data_stale_when_freshness_sla_is_exceeded(monkeypatch):
    provider = TwelveDataProvider()
    calls: list[dict] = []
    stale_seconds = settings.stale_quote_seconds + 1
    provider_timestamp = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)

    payload = {
        "symbol": "BTC/USD",
        "close": "114252.00",
        "timestamp": provider_timestamp.isoformat(),
    }
    install_fake_client(monkeypatch, payload, calls)

    quote = await provider.get_quote("BTC/USD")

    assert quote.status == QuoteStatus.STALE
    assert quote.price == 114252.00
    assert quote.provider_timestamp == provider_timestamp
    assert quote.error is not None
    assert "freshness SLA" in quote.error


@pytest.mark.asyncio
async def test_get_quote_marks_data_stale_when_provider_timestamp_is_missing(monkeypatch):
    provider = TwelveDataProvider()
    calls: list[dict] = []

    payload = {
        "symbol": "BTC/USD",
        "close": "114253.00",
    }
    install_fake_client(monkeypatch, payload, calls)

    quote = await provider.get_quote("BTC/USD")

    assert quote.status == QuoteStatus.STALE
    assert quote.price == 114253.00
    assert quote.provider_timestamp is None
    assert quote.error == "Provider timestamp unavailable; quote freshness cannot be proven."


@pytest.mark.asyncio
async def test_get_quote_rejects_future_provider_timestamp_beyond_clock_skew(monkeypatch):
    provider = TwelveDataProvider()
    calls: list[dict] = []
    provider_timestamp = datetime.now(timezone.utc) + timedelta(seconds=10)

    payload = {
        "symbol": "BTC/USD",
        "close": "114254.00",
        "timestamp": provider_timestamp.isoformat(),
    }
    install_fake_client(monkeypatch, payload, calls)

    quote = await provider.get_quote("BTC/USD")

    assert quote.status == QuoteStatus.STALE
    assert quote.price == 114254.00
    assert quote.error is not None
    assert "future" in quote.error
