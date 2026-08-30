from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, Timeframe
from app.services.indicator_series import calculate_indicator_panes


def make_candles(count: int = 260) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    candles: list[Candle] = []
    for index in range(count):
        price += 0.25 + (0.1 if index % 7 == 0 else 0)
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=price - 0.1,
                high=price + 0.2,
                low=price - 0.2,
                close=price,
                volume=1000 + index,
                symbol="BTC/USD",
                timeframe=Timeframe.HOUR_1,
                source="test_provider",
                is_complete=True,
            )
        )
    return candles


def test_indicator_panes_have_stable_contract_and_monotonic_points():
    panes = calculate_indicator_panes(make_candles())
    assert {pane["id"] for pane in panes} == {
        "rsi14",
        "macd",
        "macd_signal",
        "macd_histogram",
    }

    for pane in panes:
        assert pane["title"]
        assert pane["unit"]
        assert isinstance(pane["points"], list)
        timestamps = [point["timestamp"] for point in pane["points"]]
        assert timestamps == sorted(set(timestamps))
        assert all(point["value"] is not None for point in pane["points"])


def test_rsi_pane_is_bounded():
    rsi = next(pane for pane in calculate_indicator_panes(make_candles()) if pane["id"] == "rsi14")
    assert rsi["min"] == 0.0
    assert rsi["max"] == 100.0
    assert all(0.0 <= point["value"] <= 100.0 for point in rsi["points"])


def test_indicator_panes_reject_forming_candles():
    candles = make_candles()
    candles[-1] = candles[-1].model_copy(update={"is_complete": False})
    with pytest.raises(ValueError, match="completed candles"):
        calculate_indicator_panes(candles)
