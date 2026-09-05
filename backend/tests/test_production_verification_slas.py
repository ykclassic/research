from datetime import datetime, timezone

from scripts.verify_production_mtf import completed_candle_age_seconds
from scripts.verify_production_regime import completed_candle_close


def test_mtf_daily_age_is_measured_from_completed_close() -> None:
    candle_open = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 5, 4, 0, tzinfo=timezone.utc)

    assert completed_candle_age_seconds(candle_open, "1d", now) == 4 * 60 * 60


def test_mtf_hourly_age_is_measured_from_completed_close() -> None:
    candle_open = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 5, 4, 30, tzinfo=timezone.utc)

    assert completed_candle_age_seconds(candle_open, "1h", now) == 30 * 60


def test_regime_completed_close_matches_timeframe_duration() -> None:
    candle_open = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)

    assert completed_candle_close(candle_open, "1d") == datetime(
        2026, 9, 5, 0, 0, tzinfo=timezone.utc
    )
