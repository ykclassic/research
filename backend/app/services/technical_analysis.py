from __future__ import annotations

from math import sqrt

from app.models.market import Candle


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
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))


def _true_ranges(candles: list[Candle]) -> list[float]:
    return [
        max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - candles[i - 1].close),
            abs(candles[i].low - candles[i - 1].close),
        )
        for i in range(1, len(candles))
    ]


def _atr(candles: list[Candle], period: int = 14) -> float | None:
    true_ranges = _true_ranges(candles)
    if len(true_ranges) < period:
        return None
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
        current, previous = candles[index], candles[index - 1]
        up, down = current.high - previous.high, previous.low - current.low
        trs.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
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
        dx_values.append(
            100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0
        )
    if len(dx_values) < period:
        return None
    adx = sum(dx_values[:period]) / period
    for value in dx_values[period:]:
        adx = ((adx * (period - 1)) + value) / period
    return adx


def _stochastic(
    candles: list[Candle], period: int = 14, signal_period: int = 3
) -> tuple[float | None, float | None]:
    if len(candles) < period:
        return None, None
    k_history: list[float] = []
    for end in range(period, len(candles) + 1):
        window = candles[end - period : end]
        highest = max(c.high for c in window)
        lowest = min(c.low for c in window)
        k_history.append(
            50.0
            if highest == lowest
            else 100.0 * (candles[end - 1].close - lowest) / (highest - lowest)
        )
    k = k_history[-1]
    d = _sma(k_history, signal_period)
    return k, d


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
    if not candles or any(c.volume is None for c in candles):
        return None
    session_date = candles[-1].timestamp.date()
    session = [c for c in candles if c.timestamp.date() == session_date]
    volume = sum(c.volume or 0.0 for c in session)
    if volume <= 0:
        return None
    return sum(
        ((c.high + c.low + c.close) / 3.0) * (c.volume or 0.0) for c in session
    ) / volume


def calculate_indicators(candles: list[Candle]) -> dict[str, float | None | str]:
    """Calculate deterministic indicators from completed canonical candles.

    This function is deliberately pure: it performs no I/O, provider access,
    caching, timestamp generation, or dataset preparation. Dataset preparation
    belongs to FeatureEngine.
    """
    if not candles:
        raise ValueError("At least one completed candle is required.")
    if not all(c.is_complete for c in candles):
        raise ValueError("Technical indicators require completed candles only.")

    closes = [c.close for c in candles]
    ema20, ema50, ema200 = (
        _ema(closes, 20),
        _ema(closes, 50),
        _ema(closes, 200),
    )
    sma20, sma50, sma200 = (
        _sma(closes, 20),
        _sma(closes, 50),
        _sma(closes, 200),
    )
    rsi = _rsi(closes)

    macd_line = signal = None
    if len(closes) >= 26:
        macd_history: list[float] = []
        for end in range(26, len(closes) + 1):
            window = closes[:end]
            fast, slow = _ema(window, 12), _ema(window, 26)
            if fast is not None and slow is not None:
                macd_history.append(fast - slow)
        if macd_history:
            macd_line, signal = macd_history[-1], _ema(macd_history, 9)

    atr, adx = _atr(candles), _adx(candles)
    bb_mid = sma20
    bb_upper = bb_lower = bb_width = None
    if len(closes) >= 20:
        window = closes[-20:]
        mean = sum(window) / 20
        deviation = sqrt(sum((x - mean) ** 2 for x in window) / 20)
        bb_upper, bb_lower = mean + 2.0 * deviation, mean - 2.0 * deviation
        bb_width = (bb_upper - bb_lower) / mean if mean else None

    stoch_k, stoch_d = _stochastic(candles)
    current = candles[-1].close
    trend = "UNKNOWN"
    if ema200 is not None and ema50 is not None:
        if current > ema200 and current > ema50:
            trend = "BULLISH"
        elif current < ema200 and current < ema50:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

    return {
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "rsi14": rsi,
        "macd": macd_line,
        "macd_signal": signal,
        "macd_histogram": (
            macd_line - signal
            if macd_line is not None and signal is not None
            else None
        ),
        "atr14": atr,
        "adx14": adx,
        "bb_middle": bb_mid,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_width": bb_width,
        "stochastic_k": stoch_k,
        "stochastic_d": stoch_d,
        "obv": _obv(candles),
        "vwap": _vwap(candles),
        "trend": trend,
    }


def calculate_feature_set(dataset):
    """Compatibility entry point for the canonical FeatureEngine.

    The import is intentionally local so the numerical module can remain a
    dependency of FeatureEngine without creating a circular import at module
    initialization time.
    """
    from app.services.feature_engine import calculate_feature_set as _calculate_feature_set

    return _calculate_feature_set(dataset)
