from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.orchestrator import MarketDataOrchestrator


class CandleProvider(MarketDataProvider):
    name = "twelve_data"

    def __init__(self) -> None:
        self.fail = False
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def get_quote(self, internal_symbol: str):
        raise NotImplementedError

    async def get_candles(self, internal_symbol: str, timeframe: Timeframe, outputsize: int = 250, start_date=None, end_date=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("candle provider unavailable")
        now = datetime.now(timezone.utc)
        candles = tuple(
            Candle(
                timestamp=now - timedelta(seconds=(30 - index) * timeframe.seconds),
                open=99.0 + index * 0.01,
                high=101.0 + index * 0.01,
                low=98.0 + index * 0.01,
                close=100.0 + index * 0.01,
                volume=10.0,
                symbol=internal_symbol,
                timeframe=timeframe,
                source=self.name,
                is_complete=True,
            )
            for index in range(30)
        )
        return OHLCVDataset(
            symbol=internal_symbol,
            timeframe=timeframe,
            source=self.name,
            requested_at=now,
            provider_timestamp=now,
            candles=candles,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
            completeness_status=CompletenessStatus.COMPLETE,
        )


@pytest.mark.asyncio
async def test_canonical_candle_cache_serves_different_outputsize_without_provider_call() -> None:
    provider = CandleProvider()
    orchestrator = MarketDataOrchestrator([provider])

    original = await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1, outputsize=250)
    assert original.cache_hit is False
    assert provider.calls == 1

    provider.fail = True
    recovered = await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1, outputsize=500)

    assert recovered.cache_hit is True
    assert recovered.fallback_used is True
    assert recovered.source == "twelve_data"
    assert recovered.candle_count if hasattr(recovered, "candle_count") else len(recovered.candles) == 30
    assert len(recovered.candles) == 30
    assert provider.calls == 1
    assert recovered.freshness_status == FreshnessStatus.FRESH


@pytest.mark.asyncio
async def test_canonical_cache_is_shared_across_mtf_timeframe_requests() -> None:
    provider = CandleProvider()
    orchestrator = MarketDataOrchestrator([provider])

    await orchestrator.get_candles("BTC/USD", Timeframe.DAY_1, outputsize=250)
    await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_4, outputsize=250)
    await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1, outputsize=250)
    await orchestrator.get_candles("BTC/USD", Timeframe.MINUTE_15, outputsize=250)
    assert provider.calls == 4

    provider.fail = True
    recovered = await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1, outputsize=500)

    assert recovered.cache_hit is True
    assert recovered.fallback_used is True
    assert recovered.timeframe == Timeframe.HOUR_1
    assert recovered.source == "twelve_data"
    assert provider.calls == 4


def test_canonical_cache_returns_newest_matching_dataset() -> None:
    from app.services.cache import CanonicalMarketCache

    cache: CanonicalMarketCache[str] = CanonicalMarketCache()
    cache.set("canonical|BTC/USD|1h|recent", "newest", 60, 120)
    result = cache.get_latest("canonical|BTC/USD|1h|", allow_stale=False)

    assert result is not None
    assert result[0] == "newest"
