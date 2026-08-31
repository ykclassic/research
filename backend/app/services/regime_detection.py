from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from app.models.market import OHLCVDataset
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence
from app.services.technical_analysis import calculate_indicators


MINIMUM_CANDLES = 220
ADX_STRONG_THRESHOLD = 25.0
ADX_WEAK_THRESHOLD = 18.0
PERSISTENCE_THRESHOLD = 0.65
HIGH_VOLATILITY_PERCENTILE = 90.0
LOW_VOLATILITY_PERCENTILE = 20.0
PERSISTENCE_PERIOD = 20
VOLATILITY_LOOKBACK = 100


def _percentile_rank(values: list[float], current: float) -> float:
    """Return the empirical percentile rank of ``current`` in ``values``."""
    if not values:
        raise ValueError("Percentile calculation requires at least one value.")
    less_or_equal = sum(value <= current for value in values)
    return 100.0 * (less_or_equal - 0.5) / len(values)


def _true_range(previous_close: float, high: float, low: float) -> float:
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def _atr_series(candles, period: int = 14) -> list[float]:
    if len(candles) <= period:
        return []
    true_ranges = [
        _true_range(candles[index - 1].close, candles[index].high, candles[index].low)
        for index in range(1, len(candles))
    ]
    if len(true_ranges) < period:
        return []

    atr = sum(true_ranges[:period]) / period
    series = [atr]
    for true_range in true_ranges[period:]:
        atr = ((atr * (period - 1)) + true_range) / period
        series.append(atr)
    return series


def _bb_width_series(candles, period: int = 20) -> list[float]:
    closes = [candle.close for candle in candles]
    if len(closes) < period:
        return []

    series: list[float] = []
    for end in range(period, len(closes) + 1):
        window = closes[end - period : end]
        mean = sum(window) / period
        if mean == 0:
            continue
        variance = sum((value - mean) ** 2 for value in window) / period
        series.append((4.0 * variance**0.5) / mean)
    return series


def _trend_persistence(candles, period: int = PERSISTENCE_PERIOD) -> float:
    if len(candles) <= period:
        return 0.0
    changes = [
        candles[index].close - candles[index - 1].close
        for index in range(len(candles) - period + 1, len(candles))
    ]
    non_zero = [change for change in changes if change != 0]
    if not non_zero:
        return 0.0
    direction = 1.0 if sum(non_zero) > 0 else -1.0
    aligned = sum(change * direction > 0 for change in non_zero)
    return aligned / len(non_zero)


def _structure_bias(candles, period: int = 20) -> str:
    if len(candles) < period * 2:
        return "UNKNOWN"
    recent = candles[-period:]
    previous = candles[-period * 2 : -period]
    recent_high = sum(candle.high for candle in recent) / period
    previous_high = sum(candle.high for candle in previous) / period
    recent_low = sum(candle.low for candle in recent) / period
    previous_low = sum(candle.low for candle in previous) / period

    if recent_high > previous_high and recent_low > previous_low:
        return "BULLISH"
    if recent_high < previous_high and recent_low < previous_low:
        return "BEARISH"
    return "NEUTRAL"


def _directional_return(candles, period: int = PERSISTENCE_PERIOD) -> float | None:
    if len(candles) <= period:
        return None
    start = candles[-period - 1].close
    if start == 0:
        return None
    return (candles[-1].close / start) - 1.0


def _validate_finite_evidence(evidence: RegimeEvidence) -> None:
    for name, value in evidence.model_dump().items():
        if isinstance(value, float) and not isfinite(value):
            raise ValueError(f"Regime evidence field {name} must be finite.")


def _classify(evidence: RegimeEvidence) -> tuple[MarketRegime, float, tuple[str, ...]]:
    adx = evidence.adx14
    atr_percentile = evidence.atr_percentile
    bb_percentile = evidence.bb_width_percentile
    persistence = evidence.trend_persistence or 0.0
    direction = evidence.directional_return or 0.0

    if adx is None or atr_percentile is None or bb_percentile is None:
        return MarketRegime.UNKNOWN, 0.0, ("Insufficient deterministic evidence for classification.",)

    bullish_alignment = (
        evidence.price_above_ema_200 is True
        and evidence.ema_50_above_ema_200 is True
        and evidence.structure_bias == "BULLISH"
    )
    bearish_alignment = (
        evidence.price_above_ema_200 is False
        and evidence.ema_50_above_ema_200 is False
        and evidence.structure_bias == "BEARISH"
    )

    if adx >= ADX_STRONG_THRESHOLD and persistence >= PERSISTENCE_THRESHOLD:
        if bullish_alignment and direction > 0:
            score = min(1.0, 0.55 + 0.20 + 0.15 + 0.10 * persistence)
            return MarketRegime.STRONG_TREND_UP, score, (
                "ADX confirms a strong directional trend.",
                "Price and EMA structure are bullish.",
                "Recent price changes show persistent upside direction.",
            )
        if bearish_alignment and direction < 0:
            score = min(1.0, 0.55 + 0.20 + 0.15 + 0.10 * persistence)
            return MarketRegime.STRONG_TREND_DOWN, score, (
                "ADX confirms a strong directional trend.",
                "Price and EMA structure are bearish.",
                "Recent price changes show persistent downside direction.",
            )

    if adx >= ADX_WEAK_THRESHOLD and persistence >= 0.55 and abs(direction) > 0:
        directional = "upside" if direction > 0 else "downside"
        return MarketRegime.WEAK_TREND, min(1.0, 0.45 + 0.25 * persistence), (
            f"ADX supports a directional move without strong-trend confirmation.",
            f"Recent price movement has a {directional} direction.",
        )

    if max(atr_percentile, bb_percentile) >= HIGH_VOLATILITY_PERCENTILE:
        return MarketRegime.HIGH_VOLATILITY, min(
            1.0, 0.50 + 0.25 * max(atr_percentile, bb_percentile) / 100.0
        ), (
            "Volatility is in the extreme upper historical percentile.",
            "The volatility classification takes precedence over range/weak-trend states.",
        )

    if min(atr_percentile, bb_percentile) <= LOW_VOLATILITY_PERCENTILE:
        return MarketRegime.LOW_VOLATILITY, min(
            1.0, 0.50 + 0.25 * (100.0 - min(atr_percentile, bb_percentile)) / 100.0
        ), (
            "Volatility is in the lower historical percentile.",
            "Neither strong nor weak directional evidence is sufficient to override the volatility state.",
        )

    if adx < ADX_WEAK_THRESHOLD and persistence < PERSISTENCE_THRESHOLD:
        return MarketRegime.RANGE, min(1.0, 0.55 + (ADX_WEAK_THRESHOLD - adx) / 40.0), (
            "ADX is below the weak-trend threshold.",
            "Trend persistence is insufficient for a directional regime.",
        )

    return MarketRegime.UNKNOWN, 0.25, (
        "Evidence does not satisfy any deterministic regime rule.",
    )


def detect_regime(dataset: OHLCVDataset) -> MarketRegimeResult:
    """Classify a canonical dataset using deterministic, auditable rules.

    Regime detection is intentionally strict: a dataset containing a forming
    candle is rejected rather than silently filtering it. This prevents callers
    from accidentally believing the regime was calculated from the dataset
    they supplied when its final observation was not complete.
    """
    if any(not candle.is_complete for candle in dataset.candles):
        raise ValueError("Regime detection requires completed candles only.")

    candles = list(dataset.candles)
    if len(candles) < MINIMUM_CANDLES:
        raise ValueError(
            f"At least {MINIMUM_CANDLES} completed candles are required for regime detection."
        )

    indicators = calculate_indicators(candles)
    atr_series = _atr_series(candles)
    bb_width_series = _bb_width_series(candles)
    if not atr_series or not bb_width_series:
        raise ValueError("Insufficient volatility history for regime detection.")

    atr = indicators["atr14"]
    bb_width = indicators["bb_width"]
    ema50 = indicators["ema50"]
    ema200 = indicators["ema200"]
    adx = indicators["adx14"]
    if not all(value is not None for value in (atr, bb_width, ema50, ema200, adx)):
        return MarketRegimeResult(
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            source=dataset.source,
            calculated_at=datetime.now(timezone.utc),
            latest_completed_candle_timestamp=candles[-1].timestamp,
            regime=MarketRegime.UNKNOWN,
            confidence=0.0,
            evidence=RegimeEvidence(
                price=candles[-1].close,
                ema20=indicators["ema20"],
                ema50=ema50,
                ema200=ema200,
                adx14=adx,
                atr14=atr,
                bb_width=bb_width,
                directional_return=_directional_return(candles),
                trend_persistence=_trend_persistence(candles),
                structure_bias=_structure_bias(candles),
                completed_candles=len(candles),
            ),
            rationale=("Required indicator evidence is unavailable.",),
        )

    atr_percentile = _percentile_rank(atr_series[-VOLATILITY_LOOKBACK:], atr)
    bb_percentile = _percentile_rank(bb_width_series[-VOLATILITY_LOOKBACK:], bb_width)
    price = candles[-1].close
    evidence = RegimeEvidence(
        price=price,
        ema20=indicators["ema20"],
        ema50=ema50,
        ema200=ema200,
        price_above_ema_200=price > ema200,
        ema_50_above_ema_200=ema50 > ema200,
        adx14=adx,
        atr14=atr,
        atr_percentile=atr_percentile,
        bb_width=bb_width,
        bb_width_percentile=bb_percentile,
        directional_return=_directional_return(candles),
        trend_persistence=_trend_persistence(candles),
        structure_bias=_structure_bias(candles),
        completed_candles=len(candles),
    )
    _validate_finite_evidence(evidence)
    regime, confidence, rationale = _classify(evidence)

    return MarketRegimeResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
        calculated_at=datetime.now(timezone.utc),
        latest_completed_candle_timestamp=candles[-1].timestamp,
        regime=regime,
        confidence=confidence,
        evidence=evidence,
        rationale=rationale,
    )
