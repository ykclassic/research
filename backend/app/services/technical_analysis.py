from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[:-1], values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        true_ranges.append(max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        ))
    value = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        value = ((value * (period - 1)) + true_range) / period
    return value


def _adx(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) <= period * 2:
        return None
    trs: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        up = current.high - previous.high
        down = previous.low - current.low
        trs.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr = sum(trs[:period]) / period
    plus = sum(plus_dm[:period]) / period
    minus = sum(minus_dm[:period]) / period
    dx_values: list[float] = []
    for index in range(period, len(trs)):
        atr = ((atr * (period - 1)) + trs[index]) / period
        plus = ((plus * (period - 1)) + plus_dm[index]) / period
        minus = ((minus * (period - 1)) + minus_dm[index]) / period
        plus_di = 100.0 * plus / atr if atr else 0.0
        minus_di = 100.0 * minus / atr if atr else 0.0
        denominator = plus_di + minus_di
        dx_values.append(100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0)
    if len(dx_values) < period:
        return None
    adx = sum(dx_values[:period]) / period
    for value in dx_values[period:]:
        adx = ((adx * (period - 1)) + value) / period
    return adx


def _stochastic(candles: list[Candle], period: int = 14) -> tuple[float | None, float | None]:
    if len(candles) < period:
        return None, None
    recent = candles[-period:]
    highest = max(c.high for c in recent)
    lowest = min(c.low for c in recent)
    k = 50.0 if highest == lowest else 100.0 * (candles[-1].close - lowest) / (highest - lowest)
    # A single current %K is preferable to manufacturing historical values for the %D line.
    return k, k


def _obv(candles: list[Candle]) -> float | None:
    if not candles or any(c.volume is None for c in candles):
        return None
    obv = 0.0
    for previous, current in zip(candles[:-1], candles[1:]):
        if current.close > previous.close:
            obv += current.volume or 0.0
        elif current.close < previous.close:
            obv -= current.volume or 0.0
    return obv


def _vwap(candles: list[Candle]) -> float | None:
    usable = [c for c in candles if c.volume is not None]
    if not usable:
        return None
    volume = sum(c.volume or 0.0 for c in usable)
    if volume <= 0:
        return None
    return sum(((c.high + c.low + c.close) / 3.0) * (c.volume or 0.0) for c in usable) / volume


def calculate_indicators(candles: list[Candle]) -> dict[str, float | None | str]:
    if not candles:
        raise ValueError("At least one completed candle is required.")
    closes = [c.close for c in candles]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    rsi = _rsi(closes)
    macd_line = None
    signal = None
    if len(closes) >= 26:
        # Build the MACD history so the signal line is calculated from the same series.
        macd_history: list[float] = []
        for end in range(26, len(closes) + 1):
            window = closes[:end]
            fast = _ema(window, 12)
            slow = _ema(window, 26)
            if fast is not None and slow is not None:
                macd_history.append(fast - slow)
        if macd_history:
            macd_line = macd_history[-1]
            signal = _ema(macd_history, 9)
    atr = _atr(candles)
    adx = _adx(candles)
    bb_mid = sma20
    bb_upper = None
    bb_lower = None
    bb_width = None
    if len(closes) >= 20:
        window = closes[-20:]
        mean = sum(window) / 20
        variance = sum((x - mean) ** 2 for x in window) / 20
        deviation = sqrt(variance)
        bb_upper = mean + 2.0 * deviation
        bb_lower = mean - 2.0 * deviation
        bb_width = (bb_upper - bb_lower) / mean if mean else None
    stoch_k, stoch_d = _stochastic(candles)
    current = candles[-1].close
    trend = "UNKNOWN"
    if ema200 is not None:
        if current > ema200 and ema50 is not None and current > ema50:
            trend = "BULLISH"
        elif current < ema200 and ema50 is not None and current < ema50:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"
    return {
        "ema20": ema20, "ema50": ema50, "ema200": ema200,
        "sma20": sma20, "sma50": sma50, "sma200": sma200,
        "rsi14": rsi, "macd": macd_line, "macd_signal": signal,
        "macd_histogram": macd_line - signal if macd_line is not None and signal is not None else None,
        "atr14": atr, "adx14": adx,
        "bb_middle": bb_mid, "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_width": bb_width,
        "stochastic_k": stoch_k, "stochastic_d": stoch_d,
        "obv": _obv(candles), "vwap": _vwap(candles), "trend": trend,
    }
