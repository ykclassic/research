from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.services.candle_freshness import refresh_candle_freshness, require_current_completed_candles


def dataset(timestamp: datetime, timeframe: Timeframe = Timeframe.HOUR_1) -> OHLCVDataset:
    candle = Candle(
        timestamp=timestamp,
        open=100,
        high=101,
        low=99,
        close=100.5,
        volume=10,
        symbol="BTC/USD",
        timeframe=timeframe,
        source="twelve_data",
        is_complete=True,
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=timeframe,
        source="twelve_data",
        requested_at=timestamp,
        candles=(candle,),
        completeness_status=CompletenessStatus.COMPLETE,
    )


def test_freshness_is_measured_from_candle_close_not_open() -> None:
    now = datetime(2026, 9, 4, 8, 1, tzinfo=timezone.utc)
    opened = datetime(2026, 9, 4, 7, 0, tzinfo=timezone.utc)
    result = refresh_candle_freshness(dataset(opened), now=now)

    assert result.latest_completed_candle.timestamp == opened
    assert result.freshness_age_seconds == 60
    assert result.freshness_status is FreshnessStatus.FRESH


def test_current_hourly_completed_candle_is_not_quote_stale() -> None:
    opened = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 4, 15, 54, tzinfo=timezone.utc)
    result = refresh_candle_freshness(dataset(opened), now=now)

    assert result.freshness_age_seconds == 3240
    assert result.freshness_status is FreshnessStatus.FRESH
    assert require_current_completed_candles(result, now=now).provider_timestamp == opened


def test_years_old_completed_candles_are_rejected_for_current_research() -> None:
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    old = datetime(2020, 9, 4, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="stale"):
        require_current_completed_candles(dataset(old), now=now)


def test_incomplete_latest_candle_does_not_become_the_provenance_timestamp() -> None:
    now = datetime(2026, 9, 4, 8, 1, tzinfo=timezone.utc)
    completed_at = datetime(2026, 9, 4, 7, 0, tzinfo=timezone.utc)
    incomplete_at = completed_at + timedelta(hours=1)
    completed = dataset(completed_at).candles[0]
    incomplete = completed.model_copy(update={"timestamp": incomplete_at, "is_complete": False})
    source = dataset(completed_at).model_copy(update={"candles": (completed, incomplete)})

    result = refresh_candle_freshness(source, now=now)
    assert result.provider_timestamp == completed_at
    assert result.freshness_age_seconds == 60
