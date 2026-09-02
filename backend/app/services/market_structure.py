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
INDUCEMENT_LOOKAHEAD = 10


def _atr(candles: list[Candle], index: int, period: int = 14) -> float:
    start = max(1, index - period + 1)
    trs: list[float] = []
    for i in range(start, index + 1):
        previous_close = candles[i - 1].close
        trs.append(max(candles[i].high - candles[i].low, abs(candles[i].high - previous_close), abs(candles[i].low - previous_close)))
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
    *,
    status: StructureStatus = StructureStatus.CONFIRMED,
    invalidation: float | None = None,
    source_indexes: tuple[int, ...] | None = None,
) -> StructureEvent:
    indexes = source_indexes or (detection_index,)
    if any(index < 0 or index >= len(candles) for index in indexes):
        raise ValueError("Structure event source candle index is outside the dataset.")
    if any(index > detection_index for index in indexes):
        raise ValueError("Structure event cannot cite candles after its detection time.")
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
        delta = 0.0 if previous_high is None else abs(price - previous_high)
        events.append(_event(kind, price, detection, candles, _strength(delta, _atr(candles, detection)), invalidation=price, source_indexes=tuple(range(i - SWING_LEFT, detection + 1))))
        previous_high = price
    for i, _, price in lows:
        detection = i + SWING_RIGHT
        kind = "SWING_LOW" if previous_low is None else ("HIGHER_LOW" if price > previous_low else "LOWER_LOW")
        delta = 0.0 if previous_low is None else abs(price - previous_low)
        events.append(_event(kind, price, detection, candles, _strength(delta, _atr(candles, detection)), invalidation=price, source_indexes=tuple(range(i - SWING_LEFT, detection + 1))))
        previous_low = price
    return events


def _structure_breaks(candles: list[Candle], highs: list[tuple[int, str, float]], lows: list[tuple[int, str, float]]) -> list[StructureEvent]:
    """Detect close-throughs of latest confirmed swing levels.

    The first break establishes direction; a break against that direction is
    CHOCH and a break with it is BOS. This is an explicit research convention,
    not a claim that it is the only canonical ICT interpretation.
    """
    events: list[StructureEvent] = []
    high_iter = iter(highs)
    low_iter = iter(lows)
    next_high = next(high_iter, None)
    next_low = next(low_iter, None)
    last_high: tuple[int, float] | None = None
    last_low: tuple[int, float] | None = None
    trend: str | None = None

    for i in range(SWING_LEFT + SWING_RIGHT, len(candles)):
        while next_high is not None and next_high[0] + SWING_RIGHT <= i:
            last_high = (next_high[0], next_high[2])
            next_high = next(high_iter, None)
        while next_low is not None and next_low[0] + SWING_RIGHT <= i:
            last_low = (next_low[0], next_low[2])
            next_low = next(low_iter, None)
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
    timestamp_to_index = {c.timestamp: i for i, c in enumerate(candles)}
    for level in liquidity:
        anchor = timestamp_to_index[level.time]
        for i in range(anchor + 1, len(candles)):
            candle = candles[i]
            if level.type == "EQUAL_HIGH" and candle.high > level.price and candle.close < level.price:
                events.append(_event("LIQUIDITY_SWEEP_HIGH", level.price, i, candles, _strength(candle.high - level.price, _atr(candles, i)), invalidation=candle.high, source_indexes=tuple(timestamp_to_index[ts] for ts in (*level.source_candles, candle.timestamp))))
                break
            if level.type == "EQUAL_LOW" and candle.low < level.price and candle.close > level.price:
                events.append(_event("LIQUIDITY_SWEEP_LOW", level.price, i, candles, _strength(level.price - candle.low, _atr(candles, i)), invalidation=candle.low, source_indexes=tuple(timestamp_to_index[ts] for ts in (*level.source_candles, candle.timestamp))))
                break
    return events


def _liquidity_extensions(candles: list[Candle], liquidity: list[StructureEvent], sweeps: list[StructureEvent]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    timestamp_to_index = {c.timestamp: i for i, c in enumerate(candles)}
    for level in liquidity:
        pool_type = "LIQUIDITY_POOL_HIGH" if level.type == "EQUAL_HIGH" else "LIQUIDITY_POOL_LOW"
        detection = timestamp_to_index[level.time]
        events.append(_event(pool_type, level.price, detection, candles, level.strength, invalidation=level.invalidation, source_indexes=tuple(timestamp_to_index[ts] for ts in level.source_candles)))
    for sweep in sweeps:
        stop_type = "STOP_RUN_HIGH" if sweep.type == "LIQUIDITY_SWEEP_HIGH" else "STOP_RUN_LOW"
        detection = timestamp_to_index[sweep.time]
        events.append(_event(stop_type, sweep.price, detection, candles, sweep.strength, invalidation=sweep.invalidation, source_indexes=tuple(timestamp_to_index[ts] for ts in sweep.source_candles)))
    return events


def _displacement(candles: list[Candle]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for i in range(14, len(candles)):
        candle = candles[i]
        body = abs(candle.close - candle.open)
        atr = _atr(candles, i)
        range_size = max(candle.high - candle.low, 1e-12)
        close_location = ((candle.close - candle.low) / range_size if candle.close > candle.open else (candle.high - candle.close) / range_size)
        if body >= DISPLACEMENT_ATR * atr and close_location >= 0.65:
            bullish = candle.close > candle.open
            events.append(_event("DISPLACEMENT_BULLISH" if bullish else "DISPLACEMENT_BEARISH", candle.close, i, candles, min(1.0, body / max(2.5 * atr, 1e-12)), invalidation=candle.low if bullish else candle.high))
    return events


def _fvg(candles: list[Candle]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for i in range(2, len(candles)):
        first, _, third = candles[i - 2], candles[i - 1], candles[i]
        atr = _atr(candles, i)
        if third.low > first.high and third.low - first.high >= MIN_FVG_ATR * atr:
            events.append(_event("FVG_BULLISH", (first.high + third.low) / 2, i, candles, min(1.0, (third.low - first.high) / max(atr, 1e-12)), invalidation=first.high, source_indexes=(i - 2, i - 1, i)))
        if third.high < first.low and first.low - third.high >= MIN_FVG_ATR * atr:
            events.append(_event("FVG_BEARISH", (third.high + first.low) / 2, i, candles, min(1.0, (first.low - third.high) / max(atr, 1e-12)), invalidation=first.low, source_indexes=(i - 2, i - 1, i)))
    return events


def _order_blocks(candles: list[Candle], displacement: list[StructureEvent]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    timestamp_to_index = {c.timestamp: i for i, c in enumerate(candles)}
    for event in displacement:
        i = timestamp_to_index[event.time]
        for j in range(i - 1, max(-1, i - 4), -1):
            candle = candles[j]
            if event.type == "DISPLACEMENT_BULLISH" and candle.close < candle.open:
                events.append(_event("ORDER_BLOCK_BULLISH", (candle.open + candle.close) / 2, i, candles, event.strength, invalidation=candle.low, source_indexes=(j, i)))
                break
            if event.type == "DISPLACEMENT_BEARISH" and candle.close > candle.open:
                events.append(_event("ORDER_BLOCK_BEARISH", (candle.open + candle.close) / 2, i, candles, event.strength, invalidation=candle.high, source_indexes=(j, i)))
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
    return [_event("PREMIUM" if current > equilibrium else "DISCOUNT", current, detection, candles, min(1.0, abs(current - equilibrium) / max(high - low, 1e-12)), invalidation=equilibrium, source_indexes=(low_i, high_i, detection))]


def _inducement(candles: list[Candle], sweeps: list[StructureEvent], breaks: list[StructureEvent]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    timestamp_to_index = {c.timestamp: i for i, c in enumerate(candles)}
    for sweep in sweeps:
        sweep_i = timestamp_to_index[sweep.time]
        for structure_break in breaks:
            break_i = timestamp_to_index[structure_break.time]
            if 0 < break_i - sweep_i <= INDUCEMENT_LOOKAHEAD:
                bullish = sweep.type == "LIQUIDITY_SWEEP_LOW" and structure_break.type == "BOS_BULLISH"
                bearish = sweep.type == "LIQUIDITY_SWEEP_HIGH" and structure_break.type == "BOS_BEARISH"
                if bullish or bearish:
                    events.append(_event("INDUCEMENT_BULLISH" if bullish else "INDUCEMENT_BEARISH", sweep.price, break_i, candles, min(sweep.strength, structure_break.strength), invalidation=structure_break.invalidation, source_indexes=(sweep_i, break_i)))
                    break
    return events


def _apply_snapshot_statuses(events: list[StructureEvent], candles: list[Candle]) -> list[StructureEvent]:
    """Assign lifecycle status as of the last completed candle.

    ``time`` never moves: it remains the first candle on which the event is
    knowable. ACTIVE is used for unmitigated OB/FVG zones, BROKEN for liquidity
    pools consumed by a sweep, INVALIDATED for later threshold breaches, and
    CONFIRMED for observations without a later invalidation.
    """
    timestamp_to_index = {c.timestamp: i for i, c in enumerate(candles)}
    zone_types = {"ORDER_BLOCK_BULLISH", "ORDER_BLOCK_BEARISH", "FVG_BULLISH", "FVG_BEARISH"}
    pool_types = {"LIQUIDITY_POOL_HIGH", "LIQUIDITY_POOL_LOW"}
    sweep_types = {"LIQUIDITY_SWEEP_HIGH", "LIQUIDITY_SWEEP_LOW"}
    sweeps = [e for e in events if e.type in sweep_types]
    updated: list[StructureEvent] = []

    for event in events:
        event_i = timestamp_to_index[event.time]
        later = candles[event_i + 1 :]
        status = StructureStatus.CONFIRMED
        if event.type in pool_types:
            consumed_type = "LIQUIDITY_SWEEP_HIGH" if event.type.endswith("HIGH") else "LIQUIDITY_SWEEP_LOW"
            if any(s.type == consumed_type and abs(s.price - event.price) <= 1e-12 for s in sweeps):
                status = StructureStatus.BROKEN
        elif event.type in zone_types and event.invalidation is not None:
            invalidated = any(c.low <= event.invalidation for c in later) if event.type.endswith("BULLISH") else any(c.high >= event.invalidation for c in later)
            status = StructureStatus.INVALIDATED if invalidated else StructureStatus.ACTIVE
        elif event.invalidation is not None and event.type.startswith(("SWING_", "HIGHER_", "LOWER_")):
            invalidated = any(c.close > event.invalidation for c in later) if "HIGH" in event.type else any(c.close < event.invalidation for c in later)
            status = StructureStatus.INVALIDATED if invalidated else StructureStatus.CONFIRMED
        updated.append(event.model_copy(update={"status": status}))
    return updated


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
    liquidity_extensions = _liquidity_extensions(candles, liquidity, sweeps)
    displacement = _displacement(candles)
    fvgs = _fvg(candles)
    order_blocks = _order_blocks(candles, displacement)
    zones = _zone_events(candles, highs, lows)
    inducement = _inducement(candles, sweeps, break_events)

    events = swing_events + break_events + liquidity + liquidity_extensions + sweeps + displacement + fvgs + order_blocks + zones + inducement
    events = _apply_snapshot_statuses(events, candles)
    events.sort(key=lambda event: (event.time, event.type, event.price))
    return MarketStructureResult(symbol=dataset.symbol, timeframe=dataset.timeframe, source=dataset.source, calculated_at=datetime.now(timezone.utc), latest_candle_timestamp=candles[-1].timestamp, candle_count=len(candles), events=tuple(events))
