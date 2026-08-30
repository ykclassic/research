from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from app.models.market import Candle, OHLCVDataset
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence
from app.services.technical_analysis import _adx, _atr, _ema


MINIMUM_CANDLES = 220
EMA_PERIOD = 200
ADX_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD = 20
PERSISTENCE_PERIOD = 20
VOLATILITY_LOOKBACK = 100


def _true_range(previous: Candle, current: Candle) -> float:
    return max(
        current.high - current.low,
        abs(current.high - previous.close),
        abs(current.low - previous.close),
    )


def _atr_series(candles: list[Candle], period: int = ATR_PERIOD) -> list[float | None]:
    result: list[float | None] = [None] * len(candles)
    if len(candles) <= period:
        return result

    ranges = [
        _true_range(previous, current)
        for previous, current in zip(candles[:-1], candles[1:])
    ]
    if len(ranges) < period:
        return result

    value = sum(ranges[:period]) / period
    result[period] = value
    for range_index in range(period, len(ranges)):
        value = ((value * (period - 1)) + ranges[range_index]) / period
        result[range_index + 1] = value
    return result


def _bb_width_series(candles: list[Candle], period: int = BB_PERIOD) -> list[float | None]:
    closes = [candle.close for candle in candles]
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return result

    for index in range(period - 1, len(closes)):
        window = closes[index - period + 1 : index + 1]
        mean = sum(window) / period
        if mean == 0:
            continue
        variance = sum((value - mean) ** 2 for value in window) / period
        result[index] = (4.0 * variance**0.5) / mean
    return result


def _percentile(current: float | None, history: list[float | None]) -> float | None:
    """Return a tie-safe empirical percentile in [0, 100]."""
    if current is None or not isfinite(current):
        return None
    values = [value for value in history if value is not None and isfinite(value)]
    if not values:
        return None
    if len(values) == 1:
        return 50.0
    less = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return 100.0 * (less + 0.5 * equal) / len(values)


def _trend_persistence(closes: list[float], direction: int) -> float:
    if len(closes) < 2:
        return 0.0
    window = closes[-PERSISTENCE_PERIOD:]
    changes = [current - previous for previous, current in zip(window[:-1], window[1:])]
    if not changes:
        return 0.0
    aligned = sum(change > 0 if direction > 0 else change < 0 for change in changes)
    return aligned / len(changes)


def _structure_flags(candles: list[Candle]) -> tuple[bool, bool, bool, bool]:
    window = candles[-20:]
    midpoint = len(window) // 2
    first, second = window[:midpoint], window[midpoint:]
    first_high = max(c.high for c in first)
    second_high = max(c.high for c in second)
    first_low = min(c.low for c in first)
    second_low = min(c.low for c in second)
    return (
        second_high > first_high,
        second_low > first_low,
        second_high < first_high,
        second_low < first_low,
    )


def _ema_slope_pct(closes: list[float], period: int = 50, lookback: int = 10) -> float | None:
    if len(closes) < period + lookback:
        return None
    current = _ema(closes, period)
    previous = _ema(closes[:-lookback], period)
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


def _confidence(regime: MarketRegime, evidence: RegimeEvidence) -> float:
    adx = evidence.adx14 or 0.0
    persistence = evidence.trend_persistence or 0.0
    atr_pct = evidence.atr_percentile
    bb_pct = evidence.bb_width_percentile
    slope = abs(evidence.ema_50_slope_pct or 0.0)

    if regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN):
        adx_score = min(adx / 40.0, 1.0)
        slope_score = min(slope / 1.0, 1.0)
        score = 0.40 * adx_score + 0.35 * persistence + 0.25 * slope_score
    elif regime == MarketRegime.WEAK_TREND:
        score = 0.45 * min(adx / 30.0, 1.0) + 0.55 * persistence
    elif regime == MarketRegime.RANGE:
        adx_score = max(0.0, 1.0 - adx / 25.0)
        width_score = 1.0 - min((bb_pct or 50.0) / 100.0, 1.0)
        score = 0.60 * adx_score + 0.40 * width_score
    elif regime == MarketRegime.HIGH_VOLATILITY:
        score = max(atr_pct or 0.0, bb_pct or 0.0) / 100.0
    elif regime == MarketRegime.LOW_VOLATILITY:
        score = 1.0 - min(max(atr_pct or 50.0, bb_pct or 50.0) / 100.0, 1.0)
    else:
        return 0.0
    return round(max(0.0, min(score, 1.0)), 4)


def detect_regime(dataset: OHLCVDataset) -> MarketRegimeResult:
    """Classify a completed-candle dataset using deterministic, auditable rules.

    No provider access, caching, AI inference, or current quote is used here.
    The latest completed candle is the only observation used for classification.
    """
    completed = list(dataset.completed_candles)
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(
            f"At least {MINIMUM_CANDLES} completed candles are required for regime detection."
        )
    if any(not candle.is_complete for candle in dataset.candles):
        raise ValueError("Regime detection requires completed candles only.")

    closes = [candle.close for candle in completed]
    current = closes[-1]
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, EMA_PERIOD)
    adx = _adx(completed, ADX_PERIOD)
    atr = _atr(completed, ATR_PERIOD)
    atr_series = _atr_series(completed)
    bb_series = _bb_width_series(completed)
    atr_percentile = _percentile(atr, atr_series[-VOLATILITY_LOOKBACK:])
    bb_width = bb_series[-1]
    bb_percentile = _percentile(bb_width, bb_series[-VOLATILITY_LOOKBACK:])
    slope = _ema_slope_pct(closes)

    bullish = (
        ema50 is not None
        and ema200 is not None
        and current > ema200
        and ema50 > ema200
    )
    bearish = (
        ema50 is not None
        and ema200 is not None
        and current < ema200
        and ema50 < ema200
    )
    direction = 1 if bullish else -1 if bearish else 0
    persistence = _trend_persistence(closes, direction) if direction else 0.0
    higher_highs, higher_lows, lower_highs, lower_lows = _structure_flags(completed)

    evidence = RegimeEvidence(
        price_above_ema_200=current > ema200 if ema200 is not None else None,
        ema_50_above_ema_200=ema50 > ema200 if ema50 is not None and ema200 is not None else None,
        ema_50_slope_pct=slope,
        adx14=adx,
        atr14=atr,
        atr_percentile=atr_percentile,
        bb_width=bb_width,
        bb_width_percentile=bb_percentile,
        trend_persistence=persistence if direction else None,
        higher_highs=higher_highs,
        higher_lows=higher_lows,
        lower_highs=lower_highs,
        lower_lows=lower_lows,
    )

    if adx is None or atr_percentile is None or bb_percentile is None or ema200 is None:
        regime = MarketRegime.UNKNOWN
    elif bullish and adx >= 25.0 and persistence >= 0.60:
        regime = MarketRegime.STRONG_TREND_UP
    elif bearish and adx >= 25.0 and persistence >= 0.60:
        regime = MarketRegime.STRONG_TREND_DOWN
    elif atr_percentile >= 80.0 or bb_percentile >= 80.0:
        regime = MarketRegime.HIGH_VOLATILITY
    elif atr_percentile <= 20.0 and bb_percentile <= 20.0:
        regime = MarketRegime.LOW_VOLATILITY
    elif adx < 20.0 and atr_percentile <= 60.0 and bb_percentile <= 60.0:
        regime = MarketRegime.RANGE
    elif adx >= 20.0 and (bullish or bearish):
        regime = MarketRegime.WEAK_TREND
    else:
        regime = MarketRegime.RANGE

    return MarketRegimeResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe.value,
        source=dataset.source,
        regime=regime,
        confidence=_confidence(regime, evidence),
        calculated_at=datetime.now(timezone.utc),
        latest_candle_timestamp=completed[-1].timestamp,
        candle_count=len(completed),
        evidence=evidence,
    )
