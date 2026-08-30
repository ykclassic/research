from __future__ import annotations

from app.models.market import Candle
from app.services.technical_analysis import _ema_series


def _rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return result

    gains = [max(current - previous, 0.0) for previous, current in zip(closes[:-1], closes[1:])]
    losses = [max(previous - current, 0.0) for previous, current in zip(closes[:-1], closes[1:])]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value() -> float:
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    result[period] = value()
    for index in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[index]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[index]) / period
        result[index + 1] = value()
    return result


def _macd_series(closes: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast = _ema_series(closes, 12)
    slow = _ema_series(closes, 26)
    macd: list[float | None] = [None] * len(closes)
    compact: list[float] = []
    compact_indexes: list[int] = []
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow)):
        if fast_value is not None and slow_value is not None:
            macd[index] = fast_value - slow_value
            compact.append(macd[index])
            compact_indexes.append(index)

    signal_compact = _ema_series(compact, 9)
    signal: list[float | None] = [None] * len(closes)
    histogram: list[float | None] = [None] * len(closes)
    for compact_index, candle_index in enumerate(compact_indexes):
        signal_value = signal_compact[compact_index]
        signal[candle_index] = signal_value
        if signal_value is not None and macd[candle_index] is not None:
            histogram[candle_index] = macd[candle_index] - signal_value
    return macd, signal, histogram


def _pane(pane_id: str, title: str, unit: str, timestamps, values, minimum=None, maximum=None) -> dict:
    points = [
        {"timestamp": timestamp, "value": value}
        for timestamp, value in zip(timestamps, values)
        if value is not None
    ]
    return {
        "id": pane_id,
        "title": title,
        "unit": unit,
        "min": minimum,
        "max": maximum,
        "points": points,
    }


def calculate_indicator_panes(candles: list[Candle]) -> list[dict]:
    """Build historical indicator panes from the same completed candle set used by TA."""
    if not candles or not all(candle.is_complete for candle in candles):
        raise ValueError("Indicator panes require completed candles only.")

    timestamps = [candle.timestamp for candle in candles]
    closes = [candle.close for candle in candles]
    rsi = _rsi_series(closes)
    macd, signal, histogram = _macd_series(closes)

    return [
        _pane("rsi14", "RSI (14)", "index", timestamps, rsi, 0.0, 100.0),
        _pane("macd", "MACD", "price", timestamps, macd),
        _pane("macd_signal", "MACD Signal", "price", timestamps, signal),
        _pane("macd_histogram", "MACD Histogram", "price", timestamps, histogram),
    ]
