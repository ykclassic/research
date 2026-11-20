import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.models import Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus, Timeframe
from app.services.quote_service import QuoteService
from app.services.resilient_market_data import ResilientMarketDataOrchestrator
from app.symbols import CRYPTO_PAIRS


def _quote(symbol: str, status: QuoteStatus) -> Quote:
    return Quote(
        symbol=symbol,
        provider_symbol=symbol,
        price=None,
        timestamp=None,
        provider_timestamp=None,
        observed_at=None,
        source=None,
        status=status,
        latency_ms=None,
        cache_hit=False,
        freshness_status=FreshnessStatus.UNKNOWN,
        freshness_age_seconds=None,
        completeness_status=CompletenessStatus.INVALID,
        fallback_used=False,
        provider_attempts=(),
    )


def _live_quote(symbol: str, source: str) -> Quote:
    observed_at = datetime.now(timezone.utc)
    return Quote(
        symbol=symbol,
        provider_symbol=symbol,
        price=100.0,
        timestamp=observed_at,
        provider_timestamp=observed_at,
        observed_at=observed_at,
        source=source,
        status=QuoteStatus.LIVE,
        freshness_status=FreshnessStatus.FRESH,
        freshness_age_seconds=0.0,
        completeness_status=CompletenessStatus.COMPLETE,
        provider_attempts=(source,),
    )


class _KrakenBatch:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        self.calls.append(list(symbols))
        if "SUI/USDT" in symbols:
            raise ValueError("Kraken has no native SUI/USDT ticker mapping.")
        return [_live_quote(symbol, "kraken_public") for symbol in symbols]


class _FallbackBatch:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def get_quotes(self, symbols: list[str], force_refresh: bool = False) -> list[Quote]:
        self.calls.append(list(symbols))
        return [_live_quote(symbol, "finnhub") for symbol in symbols]


def test_quote_service_isolates_unsupported_kraken_symbol_from_supported_batch() -> None:
    service = QuoteService()
    kraken = _KrakenBatch()
    fallback = _FallbackBatch()
    service.crypto_provider = kraken
    service.orchestrator = fallback

    result = asyncio.run(service.get_quotes(list(CRYPTO_PAIRS)))

    expected_kraken_symbols = [symbol for symbol in CRYPTO_PAIRS if symbol != "SUI/USDT"]
    assert kraken.calls == [expected_kraken_symbols]
    assert fallback.calls == [["SUI/USDT"]]
    assert [quote.symbol for quote in result] == list(CRYPTO_PAIRS)
    assert {
        quote.symbol: quote.source for quote in result
    } == {
        **{symbol: "kraken_public" for symbol in expected_kraken_symbols},
        "SUI/USDT": "finnhub",
    }


def test_quote_service_skips_kraken_when_request_contains_only_unsupported_symbols() -> None:
    service = QuoteService()
    kraken = _KrakenBatch()
    fallback = _FallbackBatch()
    service.crypto_provider = kraken
    service.orchestrator = fallback

    result = asyncio.run(service.get_quotes(["SUI/USDT"]))

    assert kraken.calls == []
    assert fallback.calls == [["SUI/USDT"]]
    assert len(result) == 1
    assert result[0].symbol == "SUI/USDT"
    assert result[0].source == "finnhub"


def test_quote_service_uses_forex_fallback_for_unavailable_quote():
    delegate = AsyncMock()
    delegate.get_quote = AsyncMock(return_value=_quote("GBP/USD", QuoteStatus.UNAVAILABLE))
    service = QuoteService(orchestrator=delegate)
    fallback = _quote("GBP/USD", QuoteStatus.LIVE)
    with patch("app.services.quote_service.get_forex_quote", new=AsyncMock(return_value=fallback)) as get_fallback:
        result = asyncio.run(service.get_quote("GBP/USD"))
    assert result is fallback
    get_fallback.assert_awaited_once_with("GBP/USD")


def test_resilient_orchestrator_retries_once_with_fresh_provider_state():
    delegate = AsyncMock()
    delegate.get_candles = AsyncMock(side_effect=RuntimeError("all providers unavailable"))
    recovered = object()
    fresh = AsyncMock()
    fresh.get_candles = AsyncMock(return_value=recovered)
    proxy = ResilientMarketDataOrchestrator(delegate)
    with patch("app.services.resilient_market_data.MarketDataOrchestrator", return_value=fresh):
        result = asyncio.run(proxy.get_candles("GBP/USD", Timeframe.HOUR_1, 250))
    assert result is recovered
    delegate.get_candles.assert_awaited_once_with(
        "GBP/USD", Timeframe.HOUR_1, 250, start_date=None, end_date=None
    )
    fresh.get_candles.assert_awaited_once_with("GBP/USD", Timeframe.HOUR_1, 250)
