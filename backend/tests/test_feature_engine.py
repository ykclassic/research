from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.services.feature_engine import FeatureEngine, calculate_feature_set


def make_dataset(count: int = 30, *, incomplete_last: bool = False) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(minutes=5 * index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0 + index,
            symbol="BTC/USD",
            timeframe=Timeframe.MINUTE_5,
            source="test",
            is_complete=not (incomplete_last and index == count - 1),
        )
        for index in range(count)
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.MINUTE_5,
        source="test",
        requested_at=start,
        provider_timestamp=start,
        candles=candles,
    )


def test_feature_engine_excludes_forming_last_candle():
    dataset = make_dataset(30, incomplete_last=True)

    result = calculate_feature_set(dataset)

    assert result.candle_count == 29
    assert result.latest_candle_timestamp == dataset.candles[-2].timestamp


def test_feature_engine_rejects_incomplete_candle_before_last():
    dataset = make_dataset(30)
    candles = list(dataset.candles)
    candles[10] = candles[10].model_copy(update={"is_complete": False})
    invalid = dataset.model_copy(update={"candles": tuple(candles)})

    with pytest.raises(ValueError, match="only occur at the end"):
        calculate_feature_set(invalid)


def test_feature_engine_enforces_minimum_history():
    dataset = make_dataset(19)
    engine = FeatureEngine(minimum_candles=20)

    with pytest.raises(ValueError, match="At least 20 completed candles"):
        engine.calculate(dataset)


def test_feature_engine_is_deterministic_for_same_dataset():
    dataset = make_dataset(50)

    first = calculate_feature_set(dataset)
    second = calculate_feature_set(dataset)

    assert first.symbol == second.symbol
    assert first.timeframe == second.timeframe
    assert first.source == second.source
    assert first.latest_candle_timestamp == second.latest_candle_timestamp
    assert first.candle_count == second.candle_count
    assert first.indicators == second.indicators
    assert first.calculated_at != second.calculated_at
