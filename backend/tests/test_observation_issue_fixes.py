import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.models import Candle, Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.services.quote_service import QuoteService
from app.services.regime_detection import detect_regime
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


def test_regime_detection_ignores_incomplete_latest_candle():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(220):
        price = 100.0 + index * 0.05
        candles.append(Candle(
            timestamp=start + timedelta(hours=index),
            open=price,
            high=price + 0.2,
            low=price - 0.1,
            close=price + 0.1,
            volume=1000.0,
            symbol="BTC/USD",
            timeframe=Timeframe.HOUR_1,
            source="test",
            is_complete=True,
        ))
    candles.append(candles[-1].model_copy(update={
        "timestamp": candles[-1].timestamp + timedelta(hours=1),
        "open": candles[-1].close,
        "high": candles[-1].close + 0.2,
        "low": candles[-1].close - 0.1,
        "close": candles[-1].close + 0.1,
        "is_complete": False,
    }))
    dataset = OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test",
        requested_at=start,
        candles=tuple(candles),
    )
    result = detect_regime(dataset)
    assert result.candle_count == 220
    assert result.latest_candle_timestamp == candles[-2].timestamp
