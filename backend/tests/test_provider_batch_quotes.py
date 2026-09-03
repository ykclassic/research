import asyncio
from datetime import datetime, timezone

import httpx

from app.models import Quote, QuoteStatus
from app.providers.base import MarketDataProvider
from app.providers.errors import ProviderErrorCode, classify_provider_error
from app.providers.orchestrator import MarketDataOrchestrator
from app.providers.twelve_data import TwelveDataProvider


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, *, batch: bool = True, fail_code: ProviderErrorCode | None = None):
        self.batch_calls = 0
        self.single_calls = 0
        self.batch = batch
        self.fail_code = fail_code

    @property
    def configured(self) -> bool:
        return True

    @property
    def supports_batch_quotes(self) -> bool:
        return self.batch

    async def get_quote(self, internal_symbol: str) -> Quote:
        self.single_calls += 1
        if self.fail_code:
            return Quote(symbol=internal_symbol, provider_symbol=internal_symbol, status=QuoteStatus.UNAVAILABLE,
                         source=self.name, error=self.fail_code.value, error_code=self.fail_code)
        now = datetime.now(timezone.utc)
        return Quote(symbol=internal_symbol, provider_symbol=internal_symbol, price=100.0,
                     timestamp=now, provider_timestamp=now, observed_at=now,
                     source=self.name, status=QuoteStatus.LIVE)

    async def get_quotes(self, internal_symbols: list[str]) -> list[Quote]:
        self.batch_calls += 1
        if self.batch:
            return [await self.get_quote(symbol) for symbol in internal_symbols]
        return await super().get_quotes(internal_symbols)

    async def get_candles(self, internal_symbol, timeframe, outputsize=250, start_date=None, end_date=None):
        raise NotImplementedError


def test_orchestrator_uses_one_provider_batch_for_multiple_symbols():
    provider = FakeProvider(batch=True)
    orchestrator = MarketDataOrchestrator([provider])

    quotes = asyncio.run(orchestrator.get_quotes(["BTC/USD", "ETH/USD", "SOL/USD"]))

    assert [quote.symbol for quote in quotes] == ["BTC/USD", "ETH/USD", "SOL/USD"]
    assert provider.batch_calls == 1


def test_non_batch_provider_keeps_individual_symbol_fallback():
    provider = FakeProvider(batch=False)
    orchestrator = MarketDataOrchestrator([provider])

    quotes = asyncio.run(orchestrator.get_quotes(["BTC/USD", "ETH/USD", "SOL/USD"]))

    assert len(quotes) == 3
    assert provider.batch_calls == 1
    assert provider.single_calls == 3


def test_provider_order_matches_production_contract():
    default = MarketDataOrchestrator()
    assert [provider.name for provider in default.providers] == ["twelve_data", "alpha_vantage", "finnhub"]


def test_error_classification_distinguishes_required_categories():
    assert classify_provider_error(message="Too many requests") == ProviderErrorCode.RATE_LIMITED
    assert classify_provider_error(message="API credits exhausted") == ProviderErrorCode.QUOTA_EXHAUSTED
    assert classify_provider_error(message="Invalid API key", status_code=401) == ProviderErrorCode.AUTHENTICATION_FAILURE
    assert classify_provider_error(message="Invalid symbol") == ProviderErrorCode.SYMBOL_UNSUPPORTED
    assert classify_provider_error(httpx.ReadTimeout("timed out")) == ProviderErrorCode.PROVIDER_TIMEOUT
    assert classify_provider_error(httpx.ConnectError("connection failed")) == ProviderErrorCode.PROVIDER_UNAVAILABLE


def test_orchestrator_surfaces_all_provider_diagnostics_when_fail_closed():
    first = FakeProvider(batch=True, fail_code=ProviderErrorCode.QUOTA_EXHAUSTED)
    first.name = "twelve_data"
    second = FakeProvider(batch=True, fail_code=ProviderErrorCode.AUTHENTICATION_FAILURE)
    second.name = "alpha_vantage"
    third = FakeProvider(batch=True, fail_code=ProviderErrorCode.PROVIDER_TIMEOUT)
    third.name = "finnhub"
    orchestrator = MarketDataOrchestrator([first, second, third])

    quote = asyncio.run(orchestrator.get_quote("BTC/USD"))

    assert quote.status == QuoteStatus.UNAVAILABLE
    assert quote.error_code == ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE
    assert "twelve_data=Quota exhausted" in quote.error
    assert "alpha_vantage=Authentication failure" in quote.error
    assert "finnhub=Provider timeout" in quote.error


def test_twelve_data_batch_request_parses_quotes_and_usage(monkeypatch):
    provider = TwelveDataProvider()
    monkeypatch.setattr("app.providers.twelve_data.settings.twelve_data_api_key", "test-key")

    class FakeResponse:
        headers = httpx.Headers({"api-credits-used": "3", "api-credits-left": "5"})

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "BTC/USD": {"symbol": "BTC/USD", "close": "100.5", "timestamp": 1700000000},
                "ETH/USD": {"symbol": "ETH/USD", "close": "50.25", "timestamp": 1700000000},
            }

    class FakeClient:
        calls = []

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            self.calls.append((url, params))
            return FakeResponse()

    monkeypatch.setattr("app.providers.twelve_data.httpx.AsyncClient", FakeClient)

    quotes = asyncio.run(provider.get_quotes(["BTC/USD", "ETH/USD"]))

    assert len(quotes) == 2
    assert [quote.price for quote in quotes] == [100.5, 50.25]
    assert FakeClient.calls[0][1]["symbol"] == "BTC/USD,ETH/USD"
    assert provider.usage is not None
    assert provider.usage.credits_used == 3
    assert provider.usage.credits_remaining == 5


def test_twelve_data_does_not_retry_quota_exhaustion(monkeypatch):
    provider = TwelveDataProvider()
    monkeypatch.setattr("app.providers.twelve_data.settings.twelve_data_api_key", "test-key")
    monkeypatch.setattr("app.providers.twelve_data.settings.http_max_retries", 3)

    class FakeResponse:
        headers = httpx.Headers({"api-credits-used": "8", "api-credits-left": "0"})

        def raise_for_status(self):
            raise httpx.HTTPStatusError("429 quota", request=httpx.Request("GET", "https://example.test"), response=httpx.Response(429))

        def json(self):
            return {}

    calls = 0

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            nonlocal calls
            calls += 1
            return FakeResponse()

    monkeypatch.setattr("app.providers.twelve_data.httpx.AsyncClient", FakeClient)

    quotes = asyncio.run(provider.get_quotes(["BTC/USD", "ETH/USD"]))

    assert calls == 1
    assert all(quote.error_code == ProviderErrorCode.QUOTA_EXHAUSTED for quote in quotes)
