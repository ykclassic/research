from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.orchestrator import MarketDataOrchestrator


NOW = datetime.now(timezone.utc).replace(microsecond=0)


class FakeProvider(MarketDataProvider):
    def __init__(self, name: str, *, fail_quotes: bool = False, fail_candles: bool = False) -> None:
        self.name = name
        self.fail_quotes = fail_quotes
        self.fail_candles = fail_candles
        self.quote_calls = 0
        self.candle_calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def get_quote(self, internal_symbol: str) -> Quote:
        self.quote_calls += 1
        if self.fail_quotes:
            raise RuntimeError(f"{self.name} injected quote failure")
        return Quote(
            symbol=internal_symbol,
            provider_symbol=internal_symbol,
            price=100.0,
            timestamp=NOW,
            provider_timestamp=NOW,
            observed_at=NOW,
            source=self.name,
            status=QuoteStatus.LIVE,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0,
            completeness_status=CompletenessStatus.COMPLETE,
            latency_ms=1,
            provider_attempts=(self.name,),
        )

    async def get_candles(self, internal_symbol: str, timeframe: Timeframe, outputsize: int = 250, start_date=None, end_date=None) -> OHLCVDataset:
        self.candle_calls += 1
        if self.fail_candles:
            raise RuntimeError(f"{self.name} injected candle failure")
        candles = []
        start = NOW - timedelta(seconds=timeframe.seconds * 4)
        for index in range(5):
            timestamp = start + timedelta(seconds=timeframe.seconds * index)
            candles.append(Candle(
                timestamp=timestamp,
                open=100 + index,
                high=101 + index,
                low=99 + index,
                close=100.5 + index,
                volume=1000,
                symbol=internal_symbol,
                timeframe=timeframe,
                source=self.name,
                is_complete=True,
            ))
        return OHLCVDataset(
            symbol=internal_symbol,
            timeframe=timeframe,
            source=self.name,
            requested_at=NOW,
            provider_timestamp=candles[-1].timestamp,
            candles=tuple(candles),
            request_latency_ms=1,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0,
            completeness_status=CompletenessStatus.COMPLETE,
            provider_attempts=(self.name,),
        )


@pytest.mark.asyncio
async def test_primary_failure_selects_secondary_provider(monkeypatch):
    monkeypatch.setattr(settings, "provider_failure_threshold", 3)
    primary = FakeProvider("twelve_data", fail_quotes=True)
    secondary = FakeProvider("finnhub")
    orchestrator = MarketDataOrchestrator([primary, secondary])

    quote = await orchestrator.get_quote("BTC/USD", force_refresh=True)

    assert quote.status == QuoteStatus.LIVE
    assert quote.source == "finnhub"
    assert quote.fallback_used is True
    assert quote.provider_attempts == ("twelve_data", "finnhub")
    assert primary.quote_calls == 1
    assert secondary.quote_calls == 1


@pytest.mark.asyncio
async def test_fresh_canonical_cache_can_satisfy_injected_primary_failure():
    primary = FakeProvider("twelve_data")
    secondary = FakeProvider("finnhub", fail_quotes=True)
    orchestrator = MarketDataOrchestrator([primary, secondary])

    first = await orchestrator.get_quote("BTC/USD", force_refresh=True)
    assert first.source == "twelve_data"

    fallback = await orchestrator.get_quote(
        "BTC/USD",
        force_refresh=True,
        excluded_providers={"twelve_data"},
    )

    assert fallback.status == QuoteStatus.LIVE
    assert fallback.source == "twelve_data"
    assert fallback.cache_hit is True
    assert fallback.fallback_used is True


@pytest.mark.asyncio
async def test_circuit_opens_after_repeated_failures(monkeypatch):
    monkeypatch.setattr(settings, "provider_failure_threshold", 2)
    monkeypatch.setattr(settings, "provider_circuit_cooldown_seconds", 60)
    failing = FakeProvider("twelve_data", fail_quotes=True)
    secondary = FakeProvider("finnhub", fail_quotes=True)
    orchestrator = MarketDataOrchestrator([failing, secondary])

    for _ in range(2):
        quote = await orchestrator.get_quote("BTC/USD", force_refresh=True)
        assert quote.status == QuoteStatus.UNAVAILABLE

    assert orchestrator.provider_status()[0].circuit_open is True
    calls_after_open = failing.quote_calls
    await orchestrator.get_quote("BTC/USD", force_refresh=True)
    assert failing.quote_calls == calls_after_open


@pytest.mark.asyncio
async def test_candle_fallback_preserves_quality_metadata():
    primary = FakeProvider("twelve_data", fail_candles=True)
    secondary = FakeProvider("finnhub")
    orchestrator = MarketDataOrchestrator([primary, secondary])

    dataset = await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1, 250)

    assert dataset.source == "finnhub"
    assert dataset.fallback_used is True
    assert dataset.freshness_status == FreshnessStatus.FRESH
    assert dataset.completeness_status == CompletenessStatus.COMPLETE
    assert dataset.request_latency_ms is not None
    assert dataset.provider_attempts == ("twelve_data", "finnhub")
