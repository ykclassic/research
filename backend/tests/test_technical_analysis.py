from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.services.technical_analysis import calculate_feature_set, calculate_indicators


SYMBOL = "BTC/USD"
SOURCE = "test_provider"
TIMEFRAME = Timeframe.HOUR_1


def candles(count: int = 260, *, incomplete_last: bool = False) -> list[Candle]:
    result: list[Candle] = []
    price = 100.0
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(count):
        price += 0.25
        result.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=price - 0.1,
                high=price + 0.2,
                low=price - 0.2,
                close=price,
                volume=1000 + index,
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                source=SOURCE,
                is_complete=not (incomplete_last and index == count - 1),
            )
        )
    return result


def dataset(count: int = 260, *, incomplete_last: bool = False) -> OHLCVDataset:
    return OHLCVDataset(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        source=SOURCE,
        requested_at=datetime.now(timezone.utc),
        candles=tuple(candles(count, incomplete_last=incomplete_last)),
    )


def test_indicators_require_history_for_long_periods():
    result = calculate_indicators(candles(30))
    assert result["ema20"] is not None
    assert result["ema50"] is None
    assert result["ema200"] is None
    assert result["rsi14"] is not None


def test_indicators_calculate_long_periods_without_lookahead():
    series = candles(260)
    result = calculate_indicators(series)
    assert result["ema200"] is not None
    assert result["sma200"] is not None
    assert result["atr14"] is not None
    assert result["adx14"] is not None
    assert result["trend"] == "BULLISH"


def test_indicator_values_change_when_latest_completed_candle_changes():
    original = candles(260)
    modified = original[:-1] + [
        original[-1].model_copy(update={"close": original[-1].close + 20})
    ]
    first = calculate_indicators(original)
    second = calculate_indicators(modified)
    assert second["ema20"] != first["ema20"]
    assert second["rsi14"] != first["rsi14"]


def test_incomplete_candle_is_rejected_by_indicator_engine():
    with pytest.raises(ValueError, match="completed candles only"):
        calculate_indicators(candles(30, incomplete_last=True))


def test_empty_series_is_rejected():
    with pytest.raises(ValueError, match="completed candle"):
        calculate_indicators([])


def test_canonical_feature_set_uses_completed_candles_and_provenance():
    result = calculate_feature_set(dataset(incomplete_last=True))
    assert result.symbol == SYMBOL
    assert result.timeframe == TIMEFRAME
    assert result.source == SOURCE
    assert result.candle_count == 259
    assert result.latest_candle_timestamp == candles(260)[-2].timestamp
    assert result.calculated_at.tzinfo is not None
    assert result.indicators["ema20"] is not None
