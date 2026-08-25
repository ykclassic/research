from app.services.technical_analysis import Candle, calculate_indicators


def candles(count: int = 260) -> list[Candle]:
    result = []
    price = 100.0
    for index in range(count):
        price += 0.25
        result.append(Candle(timestamp=f"2026-01-{(index % 28) + 1:02d}T00:00:00", open=price - 0.1, high=price + 0.2, low=price - 0.2, close=price, volume=1000 + index))
    return result


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
    modified = original[:-1] + [Candle(timestamp=original[-1].timestamp, open=original[-1].open, high=original[-1].high, low=original[-1].low, close=original[-1].close + 20, volume=original[-1].volume)]
    first = calculate_indicators(original)
    second = calculate_indicators(modified)
    assert second["ema20"] != first["ema20"]
    assert second["rsi14"] != first["rsi14"]


def test_empty_series_is_rejected():
    try:
        calculate_indicators([])
    except ValueError as exc:
        assert "completed candle" in str(exc)
    else:
        raise AssertionError("Empty candle series must be rejected")
