from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, Timeframe
from app.services.technical_analysis import calculate_indicators


# Frozen numerical oracle for Phase 3.3.
# Expected values were calculated independently from the production helpers
# using the documented indicator definitions. The test does not call private
# production calculation functions to derive its expected values.
REFERENCE_VALUES = {
    "sma20": 118.9,
    "ema20": 118.92998879502693,
    "rsi14": 72.25664138955396,
    "macd": 4.682841365740757,
    "macd_signal": 4.609149001571655,
    "macd_histogram": 0.073692364169102,
    "atr14": 2.4710899196831884,
    "adx14": 40.5996165297714,
    "bb_middle": 118.9,
    "bb_upper": 126.82842985716593,
    "bb_lower": 110.97157014283408,
    "bb_width": 0.13336299171010796,
    "stochastic_k": 92.72727272727275,
    "stochastic_d": 87.95882356857969,
    "obv": 20100.0,
    "vwap": 113.78735294117647,
}


CLOSES = [
    100, 101, 100.5, 102, 101.5, 103, 104, 102.5, 105, 106,
    104.5, 107, 108, 106.5, 109, 110, 108.5, 111, 112, 110.5,
    113, 114, 112.5, 115, 116, 114.5, 117, 118, 116.5, 119,
    120, 118.5, 121, 122, 120.5, 123, 124, 122.5, 125, 126,
]


def reference_candles() -> list[Candle]:
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for index, close in enumerate(CLOSES):
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=5 * index),
                open=close - 0.2 if index % 2 == 0 else close + 0.2,
                high=close + 0.8 + (index % 3) * 0.1,
                low=close - 0.7 - (index % 2) * 0.1,
                close=close,
                volume=1000 + index * 25,
                symbol="BTC/USD",
                timeframe=Timeframe.MINUTE_5,
                source="reference_fixture",
                is_complete=True,
            )
        )
    return candles


@pytest.mark.parametrize("indicator, expected", REFERENCE_VALUES.items())
def test_indicator_matches_independent_reference_value(
    indicator: str, expected: float
):
    result = calculate_indicators(reference_candles())
    actual = result[indicator]
    assert actual is not None, f"{indicator} unexpectedly returned None"
    assert actual == pytest.approx(expected, rel=1e-10, abs=1e-10)


def test_long_period_indicators_are_explicitly_undefined_without_history():
    result = calculate_indicators(reference_candles()[:30])
    assert result["ema20"] is not None
    assert result["sma20"] is not None
    assert result["ema50"] is None
    assert result["sma50"] is None
    assert result["ema200"] is None
    assert result["sma200"] is None


def test_flat_market_edge_cases_are_deterministic():
    start = datetime(2026, 1, 3, tzinfo=timezone.utc)
    flat: list[Candle] = []
    for index in range(30):
        flat.append(
            Candle(
                timestamp=start + timedelta(minutes=5 * index),
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1000.0,
                symbol="BTC/USD",
                timeframe=Timeframe.MINUTE_5,
                source="reference_fixture",
                is_complete=True,
            )
        )

    result = calculate_indicators(flat)
    assert result["rsi14"] == pytest.approx(50.0)
    assert result["atr14"] == pytest.approx(0.0)
    assert result["adx14"] == pytest.approx(0.0)
    assert result["bb_width"] == pytest.approx(0.0)
    assert result["stochastic_k"] == pytest.approx(50.0)
    assert result["stochastic_d"] == pytest.approx(50.0)
    assert result["obv"] == pytest.approx(0.0)
    assert result["vwap"] == pytest.approx(100.0)
