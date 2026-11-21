from datetime import datetime, timedelta, timezone

from unittest.mock import AsyncMock

import pytest

from app.models.market import Candle, FreshnessStatus, OHLCVDataset, Timeframe
from app.services.research_preferences import ResearchRequestConfiguration
from app.services.research_report import ResearchReportService


class FrozenDateTime(datetime):
    current: datetime | None = None

    @classmethod
    def now(cls, tz=None):
        if cls.current is None:
            return super().now(tz)
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


def configuration() -> ResearchRequestConfiguration:
    return ResearchRequestConfiguration(
        default_asset="EUR/USD",
        default_asset_class="Forex",
        default_timeframe="1h",
        analysis_depth="Standard",
        technical_analysis_enabled=True,
        market_structure_enabled=True,
        multi_timeframe_enabled=False,
        fundamental_analysis_enabled=False,
        news_analysis_enabled=False,
        ai_interpretation_enabled=False,
        maximum_data_age_seconds=30,
        reject_stale_data=True,
        require_completed_candles=True,
        allow_cached_data_fallback=True,
    )


def candle_dataset(
    *,
    latest_open: datetime,
    now: datetime,
    completed: bool = True,
) -> OHLCVDataset:
    candle = Candle(
        timestamp=latest_open,
        open=1.08,
        high=1.09,
        low=1.07,
        close=1.085,
        volume=1000,
        symbol="EUR/USD",
        timeframe=Timeframe.HOUR_1,
        source="test-provider",
        is_complete=completed,
    )
    age = (now - (latest_open + timedelta(hours=1))).total_seconds()
    return OHLCVDataset(
        symbol="EUR/USD",
        timeframe=Timeframe.HOUR_1,
        source="test-provider",
        requested_at=now,
        provider_timestamp=latest_open,
        candles=(candle,),
        freshness_status=FreshnessStatus.STALE,
        freshness_age_seconds=max(0.0, age),
    )


@pytest.mark.asyncio
async def test_report_accepts_completed_fx_candle_during_weekend_closure(monkeypatch):
    # Saturday 11:00 New York; last completed FX candle closed Friday 16:00 ET.
    now = datetime(2026, 11, 21, 16, 0, tzinfo=timezone.utc)
    latest_open = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    dataset = candle_dataset(latest_open=latest_open, now=now)
    FrozenDateTime.current = now
    monkeypatch.setattr("app.services.research_report.datetime", FrozenDateTime)

    service = ResearchReportService()
    service.quote_service.orchestrator.get_candles = AsyncMock(return_value=dataset)

    result = await service._dataset("EUR/USD", Timeframe.HOUR_1, 300, configuration())

    assert result is dataset
    service.quote_service.orchestrator.get_candles.assert_awaited_once_with(
        "EUR/USD", Timeframe.HOUR_1, 300, allow_stale=True
    )


@pytest.mark.asyncio
async def test_report_rejects_weekend_candle_once_fx_session_reopens(monkeypatch):
    # Sunday 17:00 New York is the conventional FX reopen.
    now = datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc)
    latest_open = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    dataset = candle_dataset(latest_open=latest_open, now=now)
    FrozenDateTime.current = now
    monkeypatch.setattr("app.services.research_report.datetime", FrozenDateTime)

    service = ResearchReportService()
    service.quote_service.orchestrator.get_candles = AsyncMock(return_value=dataset)

    with pytest.raises(RuntimeError, match="no valid closed-session exception"):
        await service._dataset("EUR/USD", Timeframe.HOUR_1, 300, configuration())


@pytest.mark.asyncio
async def test_report_rejects_excessively_old_completed_candles_even_during_weekend(monkeypatch):
    now = datetime(2026, 11, 21, 16, 0, tzinfo=timezone.utc)
    latest_open = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
    dataset = candle_dataset(latest_open=latest_open, now=now)
    FrozenDateTime.current = now
    monkeypatch.setattr("app.services.research_report.datetime", FrozenDateTime)

    service = ResearchReportService()
    service.quote_service.orchestrator.get_candles = AsyncMock(return_value=dataset)

    with pytest.raises(RuntimeError, match="no valid closed-session exception"):
        await service._dataset("EUR/USD", Timeframe.HOUR_1, 300, configuration())


@pytest.mark.asyncio
async def test_report_rejects_dataset_without_completed_candles_during_weekend(monkeypatch):
    now = datetime(2026, 11, 21, 16, 0, tzinfo=timezone.utc)
    latest_open = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    dataset = candle_dataset(latest_open=latest_open, now=now, completed=False)
    FrozenDateTime.current = now
    monkeypatch.setattr("app.services.research_report.datetime", FrozenDateTime)

    service = ResearchReportService()
    service.quote_service.orchestrator.get_candles = AsyncMock(return_value=dataset)

    with pytest.raises(RuntimeError, match="No completed candles"):
        await service._dataset("EUR/USD", Timeframe.HOUR_1, 300, configuration())


def test_report_quote_policy_is_not_relaxed_by_closed_session_candle_policy():
    from app.models import Quote, QuoteStatus
    from app.services.research_report import ResearchReportService

    quote = Quote(
        symbol="EUR/USD",
        provider_symbol="EUR/USD",
        status=QuoteStatus.STALE,
        price=1.085,
        source="test-provider",
        freshness_age_seconds=3600,
    )

    with pytest.raises(RuntimeError, match="Market quote"):
        ResearchReportService._validate_quote_policy(quote, configuration())
