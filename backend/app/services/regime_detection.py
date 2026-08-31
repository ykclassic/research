from __future__ import annotations

from datetime import datetime, timezone
from statistics import pstdev

from app.models.market import OHLCVDataset
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence
from app.services.technical_analysis import calculate_indicators

MINIMUM_CANDLES = 220
ADX_STRONG = 25.0
ADX_RANGE = 20.0
PERSISTENCE_STRONG = 0.70
PERSISTENCE_WEAK = 0.50
DIRECTIONAL_RATIO_STRONG = 0.55
DIRECTIONAL_RATIO_WEAK = 0.25
VOLATILITY_HIGH_PERCENTILE = 0.80
VOLATILITY_LOW_PERCENTILE = 0.20


def _percentile_rank(values: list[float], value: float) -> float:
    """Return a mid-rank empirical percentile in [0, 1]."""
    if not values:
        return 0.5
    less = sum(candidate < value for candidate in values)
    equal = sum(candidate == value for candidate in values)
    return (less + 0.5 * equal) / len(values)


def _atr_percent_series(closes: list[float], highs: list[float], lows: list[float]) -> list[float]:
    result: list[float] = []
    for index in range(1, len(closes)):
        true_range = max(
            highs[index] - lows[index],
            abs(highs[index] - closes[index - 1]),
            abs(lows[index] - closes[index - 1]),
        )
        if closes[index] > 0:
            result.append(100.0 * true_range / closes[index])
    return result


def _bb_width_series(closes: list[float], period: int = 20) -> list[float]:
    result: list[float] = []
    for end in range(period, len(closes) + 1):
        window = closes[end - period : end]
        mean = sum(window) / period
        if mean > 0:
            result.append(4.0 * pstdev(window) / mean)
    return result


def _trend_metrics(closes: list[float], lookback: int = 40) -> tuple[str, float, float]:
    window = closes[-lookback:] if len(closes) >= lookback else closes
    changes = [current - previous for previous, current in zip(window[:-1], window[1:])]
    if not changes:
        return "UNKNOWN", 0.0, 0.0
    net = window[-1] - window[0]
    gross = sum(abs(change) for change in changes)
    ratio = abs(net) / gross if gross else 0.0
    direction = "UP" if net > 0 else "DOWN" if net < 0 else "NEUTRAL"
    aligned = sum(change > 0 for change in changes) if direction == "UP" else sum(change < 0 for change in changes)
    return direction, aligned / len(changes), ratio


def _confidence(regime: MarketRegime, evidence: RegimeEvidence) -> float:
    if regime == MarketRegime.UNKNOWN:
        return 0.0
    if regime in {MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN}:
        adx_score = min(max(((evidence.adx or 0.0) - ADX_STRONG) / 25.0, 0.0), 1.0)
        persistence_score = min(evidence.trend_persistence / PERSISTENCE_STRONG, 1.0)
        direction_score = min(evidence.directional_move_ratio / DIRECTIONAL_RATIO_STRONG, 1.0)
        return round(0.45 * adx_score + 0.35 * persistence_score + 0.20 * direction_score, 4)
    if regime == MarketRegime.WEAK_TREND:
        return round(min(1.0, 0.5 * evidence.trend_persistence + 0.5 * evidence.directional_move_ratio), 4)
    if regime == MarketRegime.HIGH_VOLATILITY:
        return round(max(evidence.atr_percentile or 0.0, evidence.bb_width_percentile or 0.0), 4)
    if regime == MarketRegime.LOW_VOLATILITY:
        return round(1.0 - min(evidence.atr_percentile or 0.5, evidence.bb_width_percentile or 0.5), 4)
    return round(min(1.0, 1.0 - (evidence.adx or 100.0) / 20.0), 4)


def detect_regime(dataset: OHLCVDataset) -> MarketRegimeResult:
    """Classify a completed-candle dataset using deterministic, auditable rules."""
    if not dataset.latest_candle.is_complete:
        raise ValueError("Regime detection requires completed candles only.")
    completed = list(dataset.completed_candles)
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for regime detection.")
    if len(completed) != len(dataset.candles):
        raise ValueError("Regime detection requires completed candles only.")

    indicators = calculate_indicators(completed)
    closes = [c.close for c in completed]
    highs = [c.high for c in completed]
    lows = [c.low for c in completed]
    current = closes[-1]
    direction, persistence, directional_ratio = _trend_metrics(closes)
    adx = indicators["adx14"]
    atr = indicators["atr14"]
    ema50 = indicators["ema50"]
    ema200 = indicators["ema200"]
    bb_width = indicators["bb_width"]

    atr_series = _atr_percent_series(closes, highs, lows)
    bb_series = _bb_width_series(closes)
    atr_percent = 100.0 * atr / current if isinstance(atr, float) and current else None
    atr_percentile = _percentile_rank(atr_series, atr_percent) if atr_percent is not None else None
    bb_width_percentile = _percentile_rank(bb_series, bb_width) if isinstance(bb_width, float) else None
    price_above_ema200 = current > ema200 if isinstance(ema200, float) else None
    ema50_above_ema200 = ema50 > ema200 if isinstance(ema50, float) and isinstance(ema200, float) else None
    evidence = RegimeEvidence(
        price=current,
        ema_50=ema50,
        ema_200=ema200,
        price_above_ema_200=price_above_ema200,
        ema_50_above_ema_200=ema50_above_ema200,
        adx=adx,
        atr=atr,
        atr_percent=atr_percent,
        atr_percentile=atr_percentile,
        bb_width=bb_width,
        bb_width_percentile=bb_width_percentile,
        trend_direction=direction,
        trend_persistence=round(persistence, 6),
        directional_move_ratio=round(directional_ratio, 6),
    )

    bullish_alignment = price_above_ema200 is True and ema50_above_ema200 is True
    bearish_alignment = price_above_ema200 is False and ema50_above_ema200 is False
    directional_conflict = (
        directional_ratio >= DIRECTIONAL_RATIO_WEAK
        and (
            (direction == "UP" and not bullish_alignment)
            or (direction == "DOWN" and not bearish_alignment)
        )
    )

    if not all(isinstance(value, float) for value in (adx, ema50, ema200, atr, bb_width)):
        regime, rule = MarketRegime.UNKNOWN, "required indicators unavailable"
    elif directional_conflict:
        regime, rule = MarketRegime.UNKNOWN, "direction conflicts with EMA structure"
    elif (
        adx >= ADX_STRONG
        and persistence >= PERSISTENCE_STRONG
        and directional_ratio >= DIRECTIONAL_RATIO_STRONG
        and direction == "UP"
        and bullish_alignment
    ):
        regime, rule = MarketRegime.STRONG_TREND_UP, "ADX>=25 + persistence>=0.70 + directional_move_ratio>=0.55 + bullish EMA alignment"
    elif (
        adx >= ADX_STRONG
        and persistence >= PERSISTENCE_STRONG
        and directional_ratio >= DIRECTIONAL_RATIO_STRONG
        and direction == "DOWN"
        and bearish_alignment
    ):
        regime, rule = MarketRegime.STRONG_TREND_DOWN, "ADX>=25 + persistence>=0.70 + directional_move_ratio>=0.55 + bearish EMA alignment"
    elif (
        atr_percentile is not None
        and (
            atr_percentile >= VOLATILITY_HIGH_PERCENTILE
            or (
                bb_width_percentile is not None
                and bb_width_percentile >= VOLATILITY_HIGH_PERCENTILE
                and atr_percentile >= 0.60
            )
        )
    ):
        regime, rule = MarketRegime.HIGH_VOLATILITY, "ATR percentile>=0.80 OR Bollinger-width percentile>=0.80 with ATR percentile>=0.60"
    elif (
        atr_percentile is not None
        and bb_width_percentile is not None
        and atr_percentile <= VOLATILITY_LOW_PERCENTILE
        and bb_width_percentile <= VOLATILITY_LOW_PERCENTILE
    ):
        regime, rule = MarketRegime.LOW_VOLATILITY, "ATR percentile<=0.20 AND Bollinger-width percentile<=0.20"
    elif (
        persistence >= PERSISTENCE_WEAK
        and directional_ratio >= DIRECTIONAL_RATIO_WEAK
        and direction == "UP"
        and bullish_alignment
    ) or (
        persistence >= PERSISTENCE_WEAK
        and directional_ratio >= DIRECTIONAL_RATIO_WEAK
        and direction == "DOWN"
        and bearish_alignment
    ):
        regime, rule = MarketRegime.WEAK_TREND, "persistence>=0.50 + directional_move_ratio>=0.25 + aligned EMA structure without strong-trend confirmation"
    elif directional_ratio < DIRECTIONAL_RATIO_WEAK:
        regime, rule = MarketRegime.RANGE, "directional_move_ratio<0.25 after trend and volatility rules"
    else:
        regime, rule = MarketRegime.UNKNOWN, "no deterministic regime rule satisfied"

    return MarketRegimeResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
        calculated_at=datetime.now(timezone.utc),
        latest_candle_timestamp=completed[-1].timestamp,
        candle_count=len(completed),
        regime=regime,
        confidence=_confidence(regime, evidence),
        evidence=evidence,
        rule=rule,
    )
