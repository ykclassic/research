from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from statistics import mean

from app.models.market import Candle, OHLCVDataset
from app.models.market_structure import MarketStructureResult, StructureEvent, StructureStatus

SWING_LEFT = 2
SWING_RIGHT = 2
EQUAL_TOLERANCE_ATR = 0.15
DISPLACEMENT_ATR = 1.5
MIN_FVG_ATR = 0.10


def _atr(candles: list[Candle], index: int, period: int = 14) -> float:
    start = max(1, index - period + 1)
    trs: list[float] = []
    for i in range(start, index + 1):
        prev_close = candles[i - 1].close
        trs.append(max(candles[i].high - candles[i].low, abs(candles[i].high - prev_close), abs(candles[i].low - prev_close)))
    return mean(trs) if trs else max(candles[index].high - candles[index].low, 1e-12)


def _strength(value: float, scale: float) -> float:
    if not isfinite(value) or scale <= 0:
        return 0.0
    return max(0.0, min(1.0, value / scale))


def _event(
    kind: str,
    price: float,
    detection_index: int,
    candles: list[Candle],
    strength: float,
    status: StructureStatus = StructureStatus.CONFIRMED,
    invalidation: float | None = None,
    source_indexes: tuple[int, ...] | None = None,
) -> StructureEvent:
    indexes = source_indexes or (detection_index,)
    return StructureEvent(
        type=kind,
        price=price,
        time=candles[detection_index].timestamp,
        timeframe=candles[detection_index].timeframe,
        strength=max(0.0, min(1.0, strength)),
        status=status,
        invalidation=invalidation,
        source_candles=tuple(candles[i].timestamp for i in indexes),
    )


def _swings(candles: list[Candle]) -> tuple[list[tuple[int, str, float]], list[tuple[int, str, float]]]:
    highs: list[tuple[int, str, float]] = []
    lows: list[tuple[int, str, float]] = []
    for i in range(SWING_LEFT, len(candles) - SWING_RIGHT):
        window = candles[i - SWING_LEFT : i + SWING_RIGHT + 1]
        if candles[i].high == max(c.high for c in window) and sum(c.high == candles[i].high for c in window) == 1:
            highs.append((i, "HIGH", candles[i].high))
        if candles[i].low == min(c.low for c in window) and sum(c.low == candles[i].low for c in window) == 1:
            lows.append((i, "LOW", candles[i].low))
    return highs, lows


def _swing_events(candles: list[Candle], highs: list[tuple[int, str, float]], lows: list[tuple[int, str, float]]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    previous_high: float | None = None
    previous_low: float | None = None
    for i, _, price in highs:
        detection = i + SWING_RIGHT
        kind = "SWING_HIGH" if previous_high is None else ("HIGHER_HIGH" if price > previous_high else "LOWER_HIGH")
        events.append(_event(kind, price, detection, candles, _strength(abs(price - (previous_high or price)), max(_atr(candles, detection), 1e-12)), invalidation=price, source_indexes=tuple(range(i - SWING_LEFT, detection + 1))))
        previous_high = price
    for i, _, price in lows:
        detection = i + SWING_RIGHT
        kind = "SWING_LOW" if previous_low is None else ("HIGHER_LOW" if price > previous_low else "LOWER_LOW")
        events.append(_event(kind, price, detection, candles, _strength(abs(price - (previous_low or price)), max(_atr(candles, detection), 1e-12)), invalidation=price, source_indexes=tuple(range(i - SWING_LEFT, detection + 1))))
        previous_low = price
    return events


def _structure_breaks(candles: list[Candle], highs: list[tuple[int, str, float]], lows: list[tuple[int, str, float]]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    last_high: tuple[int, float] | None = None
    last_low: tuple[int, float] | None = None
    trend: str | None = None
    for i in range(SWING_LEFT + SWING_RIGHT, len(candles)):
        for swing_i, _, price in highs:
            if swing_i + SWING_RIGHT <= i:
                if last_high is None or swing_i > last_high[0]:
                    last_high = (swing_i, price)
        for swing_i, _, price in lows:
            if swing_i + SWING_RIGHT <= i:
                if last_low is None or swing_i > last_low[0]:
                    last_low = (swing_i, price)
        atr = _atr(candles, i)
        if last_high and candles[i].close > last_high[1] and candles[i - 1].close <= last_high[1]:
            kind = "CHOCH_BULLISH" if trend == "BEARISH" else "BOS_BULLISH"
            events.append(_event(kind, last_high[1], i, candles, _strength(candles[i].close - last_high[1], atr), invalidation=candles[i].low, source_indexes=(last_high[0], i)))
            trend = "BULLISH"
        if last_low and candles[i].close < last_low[1] and candles[i - 1].close >= last_low[1]:
            kind = "CHOCH_BEARISH" if trend == "BULLISH" else "BOS_BEARISH"
            events.append(_event(kind, last_low[1], i, candles, _strength(last_low[1] - candles[i].close, atr), invalidation=candles[i].high, source_indexes=(last_low[0], i)))
            trend = "BEARISH"
    return events


def _equal_levels(candles: list[Candle], highs: list[tuple[int, str, float]], lows: list[tuple[int, str, float]]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for points, kind in ((highs, "EQUAL_HIGH"), (lows, "EQUAL_LOW")):
        for pos in range(1, len(points)):
            i, _, price = points[pos]
            previous_i, _, previous_price = points[pos - 1]
            tolerance = EQUAL_TOLERANCE_ATR * _atr(candles, i + SWING_RIGHT)
            if abs(price - previous_price) <= tolerance:
                level = (price + previous_price) / 2
                detection = i + SWING_RIGHT
                events.append(_event(kind, level, detection, candles, 1.0 - min(1.0, abs(price - previous_price) / max(tolerance, 1e-12)), invalidation=level, source_indexes=(previous_i, i, detection)))
    return events


def _liquidity_and_sweeps(candles: list[Candle], liquidity: list[StructureEvent]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for level in liquidity:
        level_price = level.price
        for i in range(candles.index(next(c for c in candles if c.timestamp == level.source_candles[-1])) + 1, len(candles)):
            c = candles[i]
            if level.type == "EQUAL_HIGH" and c.high > level_price and c.close < level_price:
                strength = _strength(c.high - level_price, _atr(candles, i))
                events.append(_event("LIQUIDITY_SWEEP_HIGH", level_price, i, candles, strength, invalidation=c.high, source_indexes=(i,)))
                break
            if level.type == "EQUAL_LOW" and c.low < level_price and c.close > level_price:
                strength = _strength(level_price - c.low, _atr(candles, i))
                events.append(_event("LIQUIDITY_SWEEP_LOW", level_price, i, candles, strength, invalidation=c.low, source_indexes=(i,)))
                break
    return events


def _displacement(candles: list[Candle]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for i in range(14, len(candles)):
        c = candles[i]
        body = abs(c.close - c.open)
        atr = _atr(candles, i)
        close_location = (c.close - c.low) / max(c.high - c.low, 1e-12) if c.close >= c.open else (c.high - c.close) / max(c.high - c.low, 1e-12)
        if body >= DISPLACEMENT_ATR * atr and close_location >= 0.65:
            events.append(_event("DISPLACEMENT_BULLISH" if c.close > c.open else "DISPLACEMENT_BEARISH", c.close, i, candles, min(1.0, body / max(2.5 * atr, 1e-12)), invalidation=c.low if c.close > c.open else c.high))
    return events


def _fvg(candles: list[Candle]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for i in range(2, len(candles)):
        a, _, c = candles[i - 2], candles[i - 1], candles[i]
        atr = _atr(candles, i)
        if c.low > a.high and c.low - a.high >= MIN_FVG_ATR * atr:
            events.append(_event("FVG_BULLISH", (a.high + c.low) / 2, i, candles, min(1.0, (c.low - a.high) / max(atr, 1e-12)), invalidation=a.high, source_indexes=(i - 2, i - 1, i)))
        if c.high < a.low and a.low - c.high >= MIN_FVG_ATR * atr:
            events.append(_event("FVG_BEARISH", (c.high + a.low) / 2, i, candles, min(1.0, (a.low - c.high) / max(atr, 1e-12)), invalidation=a.low, source_indexes=(i - 2, i - 1, i)))
    return events


def _order_blocks(candles: list[Candle], displacement: list[StructureEvent]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for d in displacement:
        i = next(j for j, c in enumerate(candles) if c.timestamp == d.time)
        if i < 1:
            continue
        for j in range(i - 1, max(-1, i - 4), -1):
            c = candles[j]
            if d.type == "DISPLACEMENT_BULLISH" and c.close < c.open:
                events.append(_event("ORDER_BLOCK_BULLISH", (c.open + c.close) / 2, i, candles, d.strength, invalidation=c.low, source_indexes=(j, i)))
                break
            if d.type == "DISPLACEMENT_BEARISH" and c.close > c.open:
                events.append(_event("ORDER_BLOCK_BEARISH", (c.open + c.close) / 2, i, candles, d.strength, invalidation=c.high, source_indexes=(j, i)))
                break
    return events


def _zone_events(candles: list[Candle], highs: list[tuple[int, str, float]], lows: list[tuple[int, str, float]]) -> list[StructureEvent]:
    if not highs or not lows:
        return []
    high_i, _, high = highs[-1]
    low_i, _, low = lows[-1]
    if high <= low:
        return []
    detection = max(high_i, low_i) + SWING_RIGHT
    if detection >= len(candles):
        return []
    equilibrium = (high + low) / 2
    current = candles[detection].close
    events = [_event("PREMIUM" if current > equilibrium else "DISCOUNT", current, detection, candles, min(1.0, abs(current - equilibrium) / max(high - low, 1e-12)), invalidation=equilibrium, source_indexes=(low_i, high_i, detection))]
    return events


def _inducement(candles: list[Candle], sweeps: list[StructureEvent], breaks: list[StructureEvent]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for sweep in sweeps:
        sweep_i = next(i for i, c in enumerate(candles) if c.timestamp == sweep.time)
        for br in breaks:
            br_i = next(i for i, c in enumerate(candles) if c.timestamp == br.time)
            if 0 < br_i - sweep_i <= 10:
                events.append(_event("INDUCEMENT_BULLISH" if "LOW" in sweep.type else "INDUCEMENT_BEARISH", sweep.price, br_i, candles, min(sweep.strength, br.strength), invalidation=br.invalidation, source_indexes=(sweep_i, br_i)))
                break
    return events


def analyze_market_structure(dataset: OHLCVDataset) -> MarketStructureResult:
    """Run the complete deterministic SMC research layer on completed candles only."""
    candles = list(dataset.completed_candles)
    if len(candles) < 30:
        raise ValueError("At least 30 completed candles are required for market-structure research.")
    if any(not c.is_complete for c in dataset.candles[:-1]):
        raise ValueError("Incomplete candles may only occur at the end of an OHLCV dataset.")

    highs, lows = _swings(candles)
    swing_events = _swing_events(candles, highs, lows)
    break_events = _structure_breaks(candles, highs, lows)
    liquidity = _equal_levels(candles, highs, lows)
    sweeps = _liquidity_and_sweeps(candles, liquidity)
    displacement = _displacement(candles)
    fvgs = _fvg(candles)
    order_blocks = _order_blocks(candles, displacement)
    zones = _zone_events(candles, highs, lows)
    inducement = _inducement(candles, sweeps, break_events)

    events = tuple(sorted(swing_events + break_events + liquidity + sweeps + displacement + fvgs + order_blocks + zones + inducement, key=lambda e: (e.time, e.type, e.price)))
    return MarketStructureResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
        calculated_at=datetime.now(timezone.utc),
        latest_candle_timestamp=candles[-1].timestamp,
        candle_count=len(candles),
        events=events,
    )
