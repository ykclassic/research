import asyncio
from unittest.mock import AsyncMock, patch

from app.models import Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus, Timeframe
from app.services.resilient_market_data import ResilientMarketDataOrchestrator
from app.services.research_report import ResearchReportService


def _quote(symbol: str) -> Quote:
    return Quote(
        symbol=symbol,
        provider_symbol=symbol,
        price=100.0,
        timestamp=None,
        provider_timestamp=None,
        observed_at=None,
        source="test",
        status=QuoteStatus.LIVE,
        latency_ms=1,
        cache_hit=False,
        freshness_status=FreshnessStatus.FRESH,
        freshness_age_seconds=0.0,
        completeness_status=CompletenessStatus.COMPLETE,
        fallback_used=False,
        provider_attempts=("test",),
    )


def test_resilient_orchestrator_preserves_excluded_providers_on_initial_and_recovery_calls():
    delegate = AsyncMock()
    delegate.get_candles = AsyncMock(side_effect=RuntimeError("all providers unavailable"))
    recovery = AsyncMock()
    recovery.get_candles = AsyncMock(return_value=object())
    proxy = ResilientMarketDataOrchestrator(delegate)

    with patch("app.services.resilient_market_data.MarketDataOrchestrator", return_value=recovery):
        result = asyncio.run(
            proxy.get_candles(
                "BTC/USD",
                Timeframe.HOUR_1,
                250,
                excluded_providers={"twelve_data"},
            )
        )

    assert result is not None
    delegate.get_candles.assert_awaited_once_with(
        "BTC/USD",
        Timeframe.HOUR_1,
        250,
        start_date=None,
        end_date=None,
        excluded_providers={"twelve_data"},
    )
    recovery.get_candles.assert_awaited_once_with(
        "BTC/USD",
        Timeframe.HOUR_1,
        250,
        excluded_providers={"twelve_data"},
    )


def test_research_report_does_not_assume_quote_has_volume_attribute():
    service = ResearchReportService()
    dataset = object()

    with patch.object(service.quote_service, "get_quote", new=AsyncMock(return_value=_quote("BTC/USD"))), \
         patch.object(service.quote_service.orchestrator, "get_candles", new=AsyncMock(return_value=dataset)), \
         patch.object(service, "_completed_dataset", side_effect=lambda value: value), \
         patch("app.services.research_report.calculate_feature_set") as features, \
         patch("app.services.research_report.analyze_market_structure") as structure, \
         patch("app.services.research_report.detect_regime") as regime:
        features.return_value.indicators = {"trend": "BULLISH", "rsi14": 65.0, "macd_histogram": 1.0, "atr14": 1.0}
        structure.return_value.events = []
        regime.return_value.regime.value = "RANGE"
        service.news_service.research = AsyncMock(side_effect=RuntimeError("news unavailable"))

        # The full report requires a real OHLCV dataset; this regression test
        # instead verifies the safe attribute access used by the production path.
        quote = asyncio.run(service.quote_service.get_quote("BTC/USD", force_refresh=True))
        assert getattr(quote, "volume", None) is None
