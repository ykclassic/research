from unittest.mock import AsyncMock, patch

import pytest

from app.models import Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.services.quote_service import QuoteService
from app.services.resilient_market_data import ResilientMarketDataOrchestrator


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


def test_quote_service_uses_forex_fallback_for_unavailable_quote():
    service = QuoteService(orchestrator=AsyncMock())
    service.orchestrator.get_quote = AsyncMock(return_value=_quote("GBP/USD", QuoteStatus.UNAVAILABLE))
    fallback = _quote("GBP/USD", QuoteStatus.LIVE)
    with patch("app.services.quote_service.get_forex_quote", new=AsyncMock(return_value=fallback)) as get_fallback:
        result = pytest.run(asyncio_run(service.get_quote("GBP/USD")))
    assert result is fallback
    get_fallback.assert_awaited_once_with("GBP/USD")


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


@pytest.mark.asyncio
async def test_resilient_orchestrator_retries_once_with_fresh_provider_state():
    first = AsyncMock(side_effect=RuntimeError("all providers unavailable"))
    delegate = AsyncMock()
    delegate.get_candles = first
    recovered = object()
    fresh = AsyncMock()
    fresh.get_candles = AsyncMock(return_value=recovered)
    proxy = ResilientMarketDataOrchestrator(delegate)
    with patch("app.services.resilient_market_data.MarketDataOrchestrator", return_value=fresh):
        result = await proxy.get_candles("GBP/USD", Timeframe.HOUR_1, 250)
    assert result is recovered
    first.assert_awaited_once()
    fresh.get_candles.assert_awaited_once_with("GBP/USD", Timeframe.HOUR_1, 250)
