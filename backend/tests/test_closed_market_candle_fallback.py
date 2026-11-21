from datetime import datetime, timedelta, timezone

import pytest

from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.orchestrator import MarketDataOrchestrator
from app.services.research_report import ResearchReportService


class StubCandleProvider(MarketDataProvider):
    name = "stub"

    def __init__(self, dataset: OHLCVDataset):
        self.dataset = dataset

    @property
    def configured(self) -> bool:
        return True

    async def get_quote(self, internal_symbol: str) -> Quote:
        return Quote(symbol=internal_symbol, status=QuoteStatus.UNAVAILABLE)

    async def get_candles(self, internal_symbol, timeframe, outputsize=250, start_date=None, end_date=None):
        return self.dataset


def make_dataset(*, completed_count: int = 3, total_count: int = 3) -> OHLCVDataset:
    start = datetime(2026, 11, 13, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(days=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0,
            symbol="GBP/USD",
            timeframe=Timeframe.DAY_1,
            source="stub",
            is_complete=index < completed_count,
        )
        for index in range(total_count)
    )
    return OHLCVDataset(
        symbol="GBP/USD",
        timeframe=Timeframe.DAY_1,
        source="stub",
        requested_at=start + timedelta(days=total_count),
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
        freshness_status=FreshnessStatus.STALE,
        freshness_age_seconds=172800.0,
        completeness_status=(
            CompletenessStatus.COMPLETE
            if completed_count == total_count
            else CompletenessStatus.PARTIAL
        ),
    )


@pytest.mark.asyncio
async def test_stale_completed_candles_are_admitted_only_for_closed_market(monkeypatch):
    import app.providers.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "is_market_open", lambda symbol: False)
    dataset = make_dataset()
    orchestrator = MarketDataOrchestrator(providers=[StubCandleProvider(dataset)])

    result = await orchestrator.get_candles(
        "GBP/USD", Timeframe.DAY_1, 300, allow_stale=True
    )

    assert result.freshness_status is FreshnessStatus.STALE
    assert len(result.completed_candles) == 3
    assert result.provider_timestamp == dataset.provider_timestamp


@pytest.mark.asyncio
async def test_stale_completed_candles_remain_rejected_while_market_is_open(monkeypatch):
    import app.providers.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "is_market_open", lambda symbol: True)
    orchestrator = MarketDataOrchestrator(providers=[StubCandleProvider(make_dataset())])

    with pytest.raises(RuntimeError, match="All configured market-data providers were unavailable"):
        await orchestrator.get_candles(
            "GBP/USD", Timeframe.DAY_1, 300, allow_stale=True
        )


@pytest.mark.asyncio
async def test_closed_market_does_not_admit_dataset_without_completed_candles(monkeypatch):
    import app.providers.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "is_market_open", lambda symbol: False)
    dataset = make_dataset(completed_count=0, total_count=3)
    orchestrator = MarketDataOrchestrator(providers=[StubCandleProvider(dataset)])

    with pytest.raises(RuntimeError, match="All configured market-data providers were unavailable"):
        await orchestrator.get_candles(
            "GBP/USD", Timeframe.DAY_1, 300, allow_stale=True
        )


def test_partial_dataset_keeps_only_completed_candles_for_research_calculations():
    dataset = make_dataset(completed_count=3, total_count=4)

    completed = ResearchReportService._completed_dataset(dataset)

    assert len(completed.candles) == 3
    assert all(candle.is_complete for candle in completed.candles)
    assert completed.latest_candle.timestamp == dataset.candles[-2].timestamp


def test_stale_quote_admission_remains_strict():
    stale_quote = Quote(
        symbol="GBP/USD",
        status=QuoteStatus.STALE,
        price=1.25,
        source="stub",
    )

    assert MarketDataOrchestrator._fresh_quote(stale_quote) is False
