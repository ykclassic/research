from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.market import Candle, OHLCVDataset, Timeframe


BASE = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)


def make_candle(index: int = 0, **overrides) -> Candle:
    values = {
        "timestamp": BASE + timedelta(hours=index),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000.0,
        "symbol": "BTC/USD",
        "timeframe": Timeframe.HOUR_1,
        "source": "test_provider",
        "is_complete": True,
    }
    values.update(overrides)
    return Candle(**values)


def make_dataset(*candles: Candle) -> OHLCVDataset:
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test_provider",
        requested_at=BASE,
        candles=tuple(candles),
    )


def test_candle_rejects_invalid_ohlc_range():
    with pytest.raises(ValidationError):
        make_candle(high=99.5)

    with pytest.raises(ValidationError):
        make_candle(low=100.75)


def test_candle_requires_timezone_aware_timestamp():
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_candle(timestamp=datetime(2026, 8, 25, 12))


def test_dataset_rejects_duplicate_or_non_monotonic_timestamps():
    first = make_candle(0)
    duplicate = make_candle(0)
    with pytest.raises(ValidationError, match="strictly increasing"):
        make_dataset(first, duplicate)


def test_dataset_rejects_identity_mismatch():
    with pytest.raises(ValidationError, match="symbol"):
        make_dataset(make_candle(0), make_candle(1, symbol="ETH/USD"))

    with pytest.raises(ValidationError, match="timeframe"):
        make_dataset(make_candle(0), make_candle(1, timeframe=Timeframe.DAY_1))

    with pytest.raises(ValidationError, match="source"):
        make_dataset(make_candle(0), make_candle(1, source="other_provider"))


def test_dataset_exposes_completed_candle_views():
    complete = make_candle(0, is_complete=True)
    incomplete = make_candle(1, is_complete=False)
    data = make_dataset(complete, incomplete)

    assert data.latest_candle == incomplete
    assert data.completed_candles == (complete,)
    assert data.latest_completed_candle == complete


def test_dataset_rejects_empty_candle_sequence():
    with pytest.raises(ValidationError, match="at least one candle"):
        make_dataset()
