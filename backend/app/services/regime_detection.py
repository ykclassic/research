from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from app.models.market import Candle, OHLCVDataset
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence, RegimeThresholds
from app.services.technical_analysis import calculate_indicators

MINIMUM_CANDLES = 220
WINDOW = 50
DEFAULT_THRESHOLDS = RegimeThresholds()


def _percentile_rank(values: list[float], current: float) -> float:
    if not values or not isfinite(current):
        raise ValueError("Cannot calculate percentile without finite observations.")
    rank = sum(value <= current for value in values)
    return min(1.0, max(0.0, rank / len(values)))


def _atr_percent_series(candles: list[Candle]) -> list[float]:
    values: list[float] = []
    for index in range(14, len(candles)):
        window = candles[index - 14 : index + 1]
        ranges: list[float] = []
        for position, candle in enumerate(window):
            if position == 0:
                ranges.append(candle.high - candle.low)
            else:
                previous = window[position - 1]
                ranges.append(
                    max(
                        candle.high - candle.low,
                        abs(candle.high - previous.close),
                        abs(candle.low - previous.close),
                    )
                )
        atr = sum(ranges) / len(ranges)
        if window[-1].close > 0:
            values.append(100.0 * atr / window[-1].close)
    return values


def _bb_width_series(closes: list[float], period: int = 20) -> list[float]:
    values: list[float] = []
    for index in range(period, len(closes) + 1):
        window = closes[index - period : index]
        mean = sum(window) / period
        if mean <= 0:
            continue
        deviation = (sum((value - mean) ** 2 for value in window) / period) ** 0.5
        values.append((4.0 * deviation) / mean)
    return values


def _trend_metrics(closes: list[float]) -> tuple[str, float, float]:
    sample = closes[-WINDOW:]
    if len(sample) < 2:
        return "UNKNOWN", 0.0, 0.0

    changes = [current - previous for previous, current in zip(sample[:-1], sample[1:])]
    up = sum(change > 0 for change in changes)
    down = sum(change < 0 for change in changes)
    direction = "UP" if up > down else "DOWN" if down > up else "FLAT"
    persistence = max(up, down) / len(changes)
    absolute_move = sum(abs(change) for change in changes)
    directional_ratio = (
        abs(sample[-1] - sample[0]) / absolute_move if absolute_move else 0.0
    )
    return direction, persistence, min(1.0, directional_ratio)


def _clip(value: float) -> float:
    return min(1.0, max(0.0, value))


def _confidence(regime: MarketRegime, evidence: RegimeEvidence, thresholds: RegimeThresholds) -> float:
    """Return a bounded confidence score derived only from deterministic evidence."""
    if regime is MarketRegime.UNKNOWN:
        return 0.0

    components: list[float] = []
    if evidence.adx is not None:
        components.append(_clip(evidence.adx / max(1.0, thresholds.adx_strong)))
    components.append(evidence.trend_persistence)
    components.append(evidence.directional_move_ratio)

    if evidence.atr_percentile is not None:
        components.append(evidence.atr_percentile if regime is MarketRegime.HIGH_VOLATILITY else 1.0 - evidence.atr_percentile if regime is MarketRegime.LOW_VOLATILITY else 0.5)
    if evidence.bb_width_percentile is not None:
        components.append(evidence.bb_width_percentile if regime is MarketRegime.HIGH_VOLATILITY else 1.0 - evidence.bb_width_percentile if regime is MarketRegime.LOW_VOLATILITY else 0.5)

    score = sum(components) / len(components)
    if regime is MarketRegime.RANGE:
        score = 1.0 - evidence.directional_move_ratio
    elif regime is MarketRegime.WEAK_TREND:
        score = min(score, 0.75)
    return round(_clip(score), 6)


def detect_regime(dataset: OHLCVDataset, thresholds: RegimeThresholds = DEFAULT_THRESHOLDS) -> MarketRegimeResult:
    """Classify completed candles using deterministic, auditable rules.

    The classifier performs no provider I/O and never consumes a forming candle.
    Thresholds are returned with every result so classifications are reproducible.
    """
    if not dataset.latest_candle.is_complete:
        raise ValueError("Regime detection requires completed candles only.")
    completed = list(dataset.completed_candles)
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for regime detection.")
    if len(completed) != len(dataset.candles):
        raise ValueError("Regime detection requires completed candles only.")

    indicators = calculate_indicators(completed)
    closes = [c.close for c in completed]
    current = closes[-1]
    direction, persistence, directional_ratio = _trend_metrics(closes)
    adx = indicators["adx14"]
    atr = indicators["atr14"]
    ema50 = indicators["ema50"]
    ema200 = indicators["ema200"]
    bb_width = indicators["bb_width"]

    atr_series = _atr_percent_series(completed)
    bb_series = _bb_width_series(closes)
    atr_percent = 100.0 * atr / current if isinstance(atr, float) and current > 0 else None
    atr_percentile = _percentile_rank(atr_series, atr_percent) if atr_percent is not None and atr_series else None
    bb_width_percentile = _percentile_rank(bb_series, bb_width) if isinstance(bb_width, float) and bb_series else None
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

    bullish = price_above_ema200 is True and ema50_above_ema200 is True
    bearish = price_above_ema200 is False and ema50_above_ema200 is False
    indicators_available = all(isinstance(value, float) and isfinite(value) for value in (adx, ema50, ema200, atr, bb_width))

    if not indicators_available:
        regime, rule_id, rule = MarketRegime.UNKNOWN, "R0", "required indicators unavailable"
    elif directional_ratio >= thresholds.directional_ratio_weak and (
        (direction == "UP" and not bullish) or (direction == "DOWN" and not bearish)
    ):
        regime, rule_id, rule = MarketRegime.UNKNOWN, "R1", "direction conflicts with EMA structure"
    elif (
        adx >= thresholds.adx_strong and persistence >= thresholds.persistence_strong
        and directional_ratio >= thresholds.directional_ratio_strong and direction == "UP" and bullish
    ):
        regime, rule_id, rule = MarketRegime.STRONG_TREND_UP, "R2", "ADX>=25 + persistence>=0.70 + directional_move_ratio>=0.55 + bullish EMA alignment"
    elif (
        adx >= thresholds.adx_strong and persistence >= thresholds.persistence_strong
        and directional_ratio >= thresholds.directional_ratio_strong and direction == "DOWN" and bearish
    ):
        regime, rule_id, rule = MarketRegime.STRONG_TREND_DOWN, "R3", "ADX>=25 + persistence>=0.70 + directional_move_ratio>=0.55 + bearish EMA alignment"
    elif (
        atr_percentile is not None and (
            atr_percentile >= thresholds.volatility_high_percentile
            or (bb_width_percentile is not None and bb_width_percentile >= thresholds.volatility_high_percentile and atr_percentile >= 0.60)
        )
    ):
        regime, rule_id, rule = MarketRegime.HIGH_VOLATILITY, "R4", "ATR percentile>=0.80 OR Bollinger-width percentile>=0.80 with ATR percentile>=0.60"
    elif (
        atr_percentile is not None and bb_width_percentile is not None
        and atr_percentile <= thresholds.volatility_low_percentile
        and bb_width_percentile <= thresholds.volatility_low_percentile
    ):
        regime, rule_id, rule = MarketRegime.LOW_VOLATILITY, "R5", "ATR percentile<=0.20 AND Bollinger-width percentile<=0.20"
    elif (
        persistence >= thresholds.persistence_weak and directional_ratio >= thresholds.directional_ratio_weak
        and ((direction == "UP" and bullish) or (direction == "DOWN" and bearish))
    ):
        regime, rule_id, rule = MarketRegime.WEAK_TREND, "R6", "persistence>=0.50 + directional_move_ratio>=0.25 + aligned EMA structure"
    elif directional_ratio < thresholds.directional_ratio_weak:
        regime, rule_id, rule = MarketRegime.RANGE, "R7", "directional_move_ratio<0.25 after trend and volatility rules"
    else:
        regime, rule_id, rule = MarketRegime.UNKNOWN, "R8", "no deterministic regime rule satisfied"

    return MarketRegimeResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
        calculated_at=datetime.now(timezone.utc),
        latest_candle_timestamp=completed[-1].timestamp,
        candle_count=len(completed),
        regime=regime,
        confidence=_confidence(regime, evidence, thresholds),
        evidence=evidence,
        thresholds=thresholds,
        rule_id=rule_id,
        rule=rule,
    )
