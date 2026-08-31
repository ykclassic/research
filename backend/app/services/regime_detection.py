from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from app.models.market import Candle, OHLCVDataset
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence
from app.services.technical_analysis import calculate_indicators

MINIMUM_CANDLES = 220
RULESET_VERSION = "5.1.0"
ADX_STRONG = 25.0
ADX_RANGE = 20.0
VOLATILITY_HIGH_PERCENTILE = 80.0
VOLATILITY_LOW_PERCENTILE = 20.0
PERSISTENCE_WINDOW = 20


def _percentile_rank(values: list[float], current: float) -> float:
    """Return an inclusive empirical percentile rank in [0, 100]."""
    if not values:
        return 0.0
    less_or_equal = sum(value <= current for value in values)
    return 100.0 * less_or_equal / len(values)


def _atr_value(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    tr = [
        max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - candles[i - 1].close),
            abs(candles[i].low - candles[i - 1].close),
        )
        for i in range(1, len(candles))
    ]
    if len(tr) < period:
        return None
    value = mean(tr[:period])
    for item in tr[period:]:
        value = ((value * (period - 1)) + item) / period
    return value


def _bb_width_value(candles: list[Candle], period: int = 20) -> float | None:
    if len(candles) < period:
        return None
    closes = [c.close for c in candles[-period:]]
    middle = mean(closes)
    if middle == 0:
        return None
    deviation = (mean([(value - middle) ** 2 for value in closes])) ** 0.5
    return (4.0 * deviation) / middle


def _historical_volatility_series(candles: list[Candle], calculator) -> list[float]:
    result: list[float] = []
    for end in range(20, len(candles) + 1):
        value = calculator(candles[:end])
        if value is not None:
            result.append(value)
    return result


def _trend_persistence(closes: list[float], window: int) -> tuple[float, str]:
    if len(closes) < window + 1:
        return 0.0, "UNKNOWN"
    changes = [current - previous for previous, current in zip(closes[-window - 1 : -1], closes[-window:])]
    positive = sum(change > 0 for change in changes)
    negative = sum(change < 0 for change in changes)
    up_ratio = positive / window
    down_ratio = negative / window
    if up_ratio >= 0.6:
        return up_ratio, "BULLISH"
    if down_ratio >= 0.6:
        return down_ratio, "BEARISH"
    return max(up_ratio, down_ratio), "NEUTRAL"


def _structure(candles: list[Candle], window: int = 20) -> tuple[str, int, int, int, int]:
    recent = candles[-window:]
    if len(recent) < 4:
        return "UNKNOWN", 0, 0, 0, 0
    highs = [c.high for c in recent]
    lows = [c.low for c in recent]
    hh = sum(b > a for a, b in zip(highs[:-1], highs[1:]))
    hl = sum(b > a for a, b in zip(lows[:-1], lows[1:]))
    lh = sum(b < a for a, b in zip(highs[:-1], highs[1:]))
    ll = sum(b < a for a, b in zip(lows[:-1], lows[1:]))
    if hh >= 10 and hl >= 10:
        return "BULLISH", hh, hl, lh, ll
    if lh >= 10 and ll >= 10:
        return "BEARISH", hh, hl, lh, ll
    return "MIXED", hh, hl, lh, ll


def _confidence(regime: MarketRegime, evidence: RegimeEvidence) -> float:
    scores: list[float] = []
    if regime in (MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN):
        scores.append(min((evidence.adx14 or 0.0) / 50.0, 1.0))
        scores.append(evidence.trend_persistence or 0.0)
        scores.append(1.0 if evidence.structure_direction in ("BULLISH", "BEARISH") else 0.0)
        aligned = evidence.price_above_ema200 is not None and evidence.ema50_above_ema200 is not None
        scores.append(1.0 if aligned else 0.0)
    elif regime == MarketRegime.RANGE:
        scores.append(max(0.0, 1.0 - (evidence.adx14 or 0.0) / 25.0))
        scores.append(1.0 if evidence.structure_direction in ("MIXED", "NEUTRAL") else 0.5)
    elif regime in (MarketRegime.HIGH_VOLATILITY, MarketRegime.LOW_VOLATILITY):
        percentiles = [p / 100.0 for p in (evidence.atr_percentile, evidence.bb_width_percentile) if p is not None]
        if percentiles:
            distance = max(abs(p - 0.5) for p in percentiles) * 2.0
            scores.append(distance)
    else:
        return 0.0
    return round(max(0.0, min(1.0, sum(scores) / len(scores))), 4) if scores else 0.0


def detect_regime(dataset: OHLCVDataset) -> MarketRegimeResult:
    """Classify completed candles using deterministic, auditable rules.

    The engine has no provider, quote, cache, network, or AI dependencies.
    A forming candle is never silently discarded: its presence is a contract
    violation for regime detection because the caller must provide the exact
    completed-candle dataset used for the calculation.
    """
    if not dataset.candles[-1].is_complete:
        raise ValueError("Regime detection requires completed candles only.")
    if any(not candle.is_complete for candle in dataset.candles):
        raise ValueError("Regime detection requires completed candles only.")
    completed = list(dataset.candles)
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(
            f"At least {MINIMUM_CANDLES} completed candles are required for regime detection."
        )

    indicators = calculate_indicators(completed)
    atr = _atr_value(completed)
    bb_width = _bb_width_value(completed)
    atr_series = _historical_volatility_series(completed, _atr_value)
    bb_series = _historical_volatility_series(completed, _bb_width_value)
    atr_percentile = _percentile_rank(atr_series, atr) if atr is not None else None
    bb_percentile = _percentile_rank(bb_series, bb_width) if bb_width is not None else None

    closes = [c.close for c in completed]
    price = closes[-1]
    ema50 = indicators.get("ema50")
    ema200 = indicators.get("ema200")
    adx = indicators.get("adx14")
    persistence, persistence_direction = _trend_persistence(closes, PERSISTENCE_WINDOW)
    structure_direction, hh, hl, lh, ll = _structure(completed)

    evidence = RegimeEvidence(
        price=price,
        ema50=ema50,
        ema200=ema200,
        price_above_ema200=price > ema200 if ema200 is not None else None,
        ema50_above_ema200=ema50 > ema200 if ema50 is not None and ema200 is not None else None,
        adx14=adx,
        atr14=atr,
        atr_percentile=atr_percentile,
        bb_width=bb_width,
        bb_width_percentile=bb_percentile,
        trend_persistence=persistence,
        structure_direction=structure_direction,
        higher_highs=hh,
        higher_lows=hl,
        lower_highs=lh,
        lower_lows=ll,
    )

    bullish_alignment = (
        ema50 is not None and ema200 is not None and price > ema200 and ema50 > ema200
    )
    bearish_alignment = (
        ema50 is not None and ema200 is not None and price < ema200 and ema50 < ema200
    )
    strong_up = bullish_alignment and adx is not None and adx >= ADX_STRONG and persistence_direction == "BULLISH" and structure_direction == "BULLISH"
    strong_down = bearish_alignment and adx is not None and adx >= ADX_STRONG and persistence_direction == "BEARISH" and structure_direction == "BEARISH"
    high_vol = any(p is not None and p >= VOLATILITY_HIGH_PERCENTILE for p in (atr_percentile, bb_percentile))
    low_vol = all(p is not None and p <= VOLATILITY_LOW_PERCENTILE for p in (atr_percentile, bb_percentile))

    if strong_up:
        regime = MarketRegime.STRONG_TREND_UP
    elif strong_down:
        regime = MarketRegime.STRONG_TREND_DOWN
    elif high_vol:
        regime = MarketRegime.HIGH_VOLATILITY
    elif low_vol:
        regime = MarketRegime.LOW_VOLATILITY
    elif adx is not None and adx < ADX_RANGE and structure_direction in ("MIXED", "NEUTRAL"):
        regime = MarketRegime.RANGE
    elif adx is not None and (bullish_alignment or bearish_alignment):
        regime = MarketRegime.WEAK_TREND
    else:
        regime = MarketRegime.UNKNOWN

    return MarketRegimeResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe.value,
        source=dataset.source,
        calculated_at=datetime.now(timezone.utc),
        latest_completed_candle_timestamp=completed[-1].timestamp,
        candle_count=len(completed),
        regime=regime,
        confidence=_confidence(regime, evidence),
        evidence=evidence,
        ruleset_version=RULESET_VERSION,
    )
