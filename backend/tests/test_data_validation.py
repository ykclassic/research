from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.services.data_validation import validate_ohlcv_dataset


START = datetime(2026, 8, 25, tzinfo=timezone.utc)


def candle(index: int) -> Candle:
    return Candle(
        timestamp=START + timedelta(hours=index),
        open=100 + index,
        high=101 + index,
        low=99 + index,
        close=100.5 + index,
        volume=1000,
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test_provider",
        is_complete=True,
    )


def data(*candles: Candle) -> OHLCVDataset:
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test_provider",
        requested_at=START,
        candles=tuple(candles),
    )


def test_validation_accepts_ordered_dataset():
    dataset = data(candle(0), candle(1), candle(2))
    assert validate_ohlcv_dataset(dataset) is dataset


def test_validation_can_require_contiguous_candles():
    dataset = data(candle(0), candle(2))
    with pytest.raises(ValueError, match="timestamp gap"):
        validate_ohlcv_dataset(dataset, require_contiguous=True)


def test_validation_allows_non_contiguous_dataset_by_default():
    dataset = data(candle(0), candle(2))
    assert validate_ohlcv_dataset(dataset) is dataset
