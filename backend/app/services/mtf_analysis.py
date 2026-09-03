from __future__ import annotations

from datetime import datetime, timezone

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.models.market_structure import StructureEvent
from app.models.mtf import MTFBias, MTFResearchConclusion, MTFState, MTFTimeframeAnalysis, MultiTimeframeResult
from app.services.technical_analysis import calculate_indicators

REQUIRED_TIMEFRAMES = (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15)
MINIMUM_CANDLES = 30


def _direction_from_events(events: tuple[StructureEvent, ...]) -> MTFBias:
    bullish = sum(event.strength for event in events if event.type == "BOS_BULLISH")
    bearish = sum(event.strength for event in events if event.type == "BOS_BEARISH")
    bullish_choch = sum(event.strength for event in events if event.type == "CHOCH_BULLISH")
    bearish_choch = sum(event.strength for event in events if event.type == "CHOCH_BEARISH")
    if bullish + bullish_choch > bearish + bearish_choch:
        return MTFBias.BULLISH
    if bearish + bearish_choch > bullish + bullish_choch:
        return MTFBias.BEARISH
    return MTFBias.NEUTRAL


def _latest(events: tuple[StructureEvent, ...], *types: str) -> StructureEvent | None:
    matches = [event for event in events if event.type in types]
    return max(matches, key=lambda event: event.time) if matches else None


def _active_demand(events: tuple[StructureEvent, ...]) -> bool:
    return any(event.type in {"ORDER_BLOCK_BULLISH", "FVG_BULLISH"} and event.status.value == "ACTIVE" for event in events)


def _active_supply(events: tuple[StructureEvent, ...]) -> bool:
    return any(event.type in {"ORDER_BLOCK_BEARISH", "FVG_BEARISH"} and event.status.value == "ACTIVE" for event in events)


def _in_zone(candle: Candle, events: tuple[StructureEvent, ...], bullish: bool) -> bool:
    types = {"ORDER_BLOCK_BULLISH", "FVG_BULLISH"} if bullish else {"ORDER_BLOCK_BEARISH", "FVG_BEARISH"}
    for event in events:
        if event.type not in types or event.status.value != "ACTIVE":
            continue
        if event.invalidation is None:
            continue
        if bullish and candle.low <= event.price and candle.high >= event.invalidation:
            return True
        if not bullish and candle.low <= event.invalidation and candle.high >= event.price:
            return True
    return False


def _daily_analysis(dataset: OHLCVDataset, events: tuple[StructureEvent, ...]) -> MTFTimeframeAnalysis:
    candles = list(dataset.completed_candles)
    indicators = calculate_indicators(candles)
    trend = indicators.get("trend")
    event_bias = _direction_from_events(events)
    if trend == "BULLISH":
        bias = MTFBias.BULLISH
        evidence = ["Price is above EMA20/EMA50/EMA200 trend stack."]
    elif trend == "BEARISH":
        bias = MTFBias.BEARISH
        evidence = ["Price is below EMA20/EMA50/EMA200 trend stack."]
    else:
        bias = event_bias
        evidence = ["EMA trend stack is not decisive; structure events provide the directional bias."]
    if event_bias != MTFBias.NEUTRAL:
        evidence.append(f"Confirmed structure bias: {event_bias.value}.")
    confidence = 0.70 if trend in {"BULLISH", "BEARISH"} else 0.55
    if event_bias == bias and event_bias != MTFBias.NEUTRAL:
        confidence += 0.10
    return MTFTimeframeAnalysis(timeframe=Timeframe.DAY_1, bias=bias, state=MTFState.DAILY_BIAS, conclusion=f"Daily └── {bias.value.title()}", confidence=min(confidence, 1.0), latest_candle_timestamp=candles[-1].timestamp, source=dataset.source, candle_count=len(candles), evidence=tuple(evidence))


def _h4_analysis(dataset: OHLCVDataset, events: tuple[StructureEvent, ...], daily: MTFBias) -> MTFTimeframeAnalysis:
    candles = list(dataset.completed_candles)
    indicators = calculate_indicators(candles)
    trend = indicators.get("trend")
    bias = MTFBias.BULLISH if trend == "BULLISH" else MTFBias.BEARISH if trend == "BEARISH" else _direction_from_events(events)
    confidence = 0.65 if bias != MTFBias.NEUTRAL else 0.40
    evidence = [f"H4 trend state: {bias.value}."]
    if bias == daily and bias != MTFBias.NEUTRAL:
        confidence += 0.15
        evidence.append("H4 agrees with the Daily directional bias.")
    else:
        evidence.append("H4 does not fully confirm the Daily bias.")
    return MTFTimeframeAnalysis(timeframe=Timeframe.HOUR_4, bias=bias, state=MTFState.H4_TREND, conclusion=f"H4 └── {bias.value.title()} Trend", confidence=min(confidence, 1.0), latest_candle_timestamp=candles[-1].timestamp, source=dataset.source, candle_count=len(candles), evidence=tuple(evidence))


def _h1_analysis(dataset: OHLCVDataset, events: tuple[StructureEvent, ...], h4: MTFBias) -> MTFTimeframeAnalysis:
    candles = list(dataset.completed_candles)
    latest = candles[-1]
    demand = _in_zone(latest, events, True)
    supply = _in_zone(latest, events, False)
    if h4 == MTFBias.BULLISH and demand:
        state, bias, conclusion = MTFState.H1_PULLBACK, MTFBias.BULLISH, "H1 └── Pullback into demand"
        evidence = ("Latest H1 candle overlaps an active bullish OB/FVG demand zone.", "H4 directional bias is bullish.")
        confidence = 0.82
    elif h4 == MTFBias.BEARISH and supply:
        state, bias, conclusion = MTFState.H1_PULLBACK, MTFBias.BEARISH, "H1 └── Pullback into supply"
        evidence = ("Latest H1 candle overlaps an active bearish OB/FVG supply zone.", "H4 directional bias is bearish.")
        confidence = 0.82
    else:
        local = _direction_from_events(events)
        bias = local if local != MTFBias.NEUTRAL else h4
        state = MTFState.H1_CONTINUATION if bias == h4 and bias != MTFBias.NEUTRAL else MTFState.H1_NEUTRAL
        conclusion = f"H1 └── {state.value.replace('H1_', '').replace('_', ' ').title()}"
        evidence = ("No current active demand/supply pullback was confirmed at the latest H1 candle.",)
        confidence = 0.58 if state != MTFState.H1_NEUTRAL else 0.40
    return MTFTimeframeAnalysis(timeframe=Timeframe.HOUR_1, bias=bias, state=state, conclusion=conclusion, confidence=confidence, latest_candle_timestamp=latest.timestamp, source=dataset.source, candle_count=len(candles), evidence=evidence)


def _m15_analysis(dataset: OHLCVDataset, events: tuple[StructureEvent, ...], h1: MTFBias) -> MTFTimeframeAnalysis:
    candles = list(dataset.completed_candles)
    bullish_bos = _latest(events, "BOS_BULLISH", "CHOCH_BULLISH")
    bearish_bos = _latest(events, "BOS_BEARISH", "CHOCH_BEARISH")
    latest_event = max([event for event in (bullish_bos, bearish_bos) if event is not None], key=lambda event: event.time, default=None)
    if latest_event and latest_event.type in {"BOS_BULLISH", "CHOCH_BULLISH"} and h1 == MTFBias.BULLISH:
        state, bias, conclusion = MTFState.M15_BULLISH_BOS, MTFBias.BULLISH, "M15 └── Bullish BOS"
        confidence = 0.88 if latest_event.type == "BOS_BULLISH" else 0.78
        evidence = (f"Latest bullish structure break detected at {latest_event.price:.8g}.", "M15 direction agrees with H1.")
    elif latest_event and latest_event.type in {"BOS_BEARISH", "CHOCH_BEARISH"} and h1 == MTFBias.BEARISH:
        state, bias, conclusion = MTFState.M15_BEARISH_BOS, MTFBias.BEARISH, "M15 └── Bearish BOS"
        confidence = 0.88 if latest_event.type == "BOS_BEARISH" else 0.78
        evidence = (f"Latest bearish structure break detected at {latest_event.price:.8g}.", "M15 direction agrees with H1.")
    else:
        bias = _direction_from_events(events)
        state, conclusion = MTFState.M15_NEUTRAL, f"M15 └── {bias.value.title()} / Awaiting confirmation"
        confidence = 0.45
        evidence = ("No latest M15 structure break aligned with the H1 directional bias.",)
    return MTFTimeframeAnalysis(timeframe=Timeframe.MINUTE_15, bias=bias, state=state, conclusion=conclusion, confidence=confidence, latest_candle_timestamp=candles[-1].timestamp, source=dataset.source, candle_count=len(candles), evidence=evidence)


def _research(daily: MTFTimeframeAnalysis, h4: MTFTimeframeAnalysis, h1: MTFTimeframeAnalysis, m15: MTFTimeframeAnalysis) -> MTFResearchConclusion:
    analyses = (daily, h4, h1, m15)
    directional = [item.bias for item in analyses]
    candidates = [bias for bias in (MTFBias.BULLISH, MTFBias.BEARISH) if all(bias == current for current in directional)]
    bias = candidates[0] if candidates else (h4.bias if h4.bias != MTFBias.NEUTRAL else daily.bias)
    aligned = sum(item.bias == bias and item.bias != MTFBias.NEUTRAL for item in analyses)
    alignment_count = aligned
    base = sum(item.confidence for item in analyses) / len(analyses)
    confidence = base * (0.65 + 0.35 * alignment_count / 4)
    if alignment_count == 4:
        confidence = min(0.99, confidence + 0.05)
    if bias == MTFBias.BULLISH and h1.state == MTFState.H1_PULLBACK and m15.state == MTFState.M15_BULLISH_BOS:
        primary = "H1 demand + M15 bullish BOS"
        invalidation = "H1 structure break"
    elif bias == MTFBias.BEARISH and h1.state == MTFState.H1_PULLBACK and m15.state == MTFState.M15_BEARISH_BOS:
        primary = "H1 supply + M15 bearish BOS"
        invalidation = "H1 structure break"
    else:
        primary = "No fully confirmed multi-timeframe setup"
        invalidation = "Nearest confirmed H1 structure level"
    conclusion = f"MTF Alignment: {alignment_count}/4\nBias: {bias.value.title()}\nConfidence: {confidence * 100:.0f}%\nPrimary setup: {primary}\nInvalidation: {invalidation}"
    return MTFResearchConclusion(alignment_count=alignment_count, bias=bias, confidence=confidence, primary_setup=primary, invalidation=invalidation, conclusion=conclusion)


def analyze_multi_timeframe(datasets: dict[Timeframe, OHLCVDataset], structures: dict[Timeframe, tuple[StructureEvent, ...]]) -> MultiTimeframeResult:
    missing = [timeframe.value for timeframe in REQUIRED_TIMEFRAMES if timeframe not in datasets or timeframe not in structures]
    if missing:
        raise ValueError(f"Missing required MTF timeframe(s): {', '.join(missing)}")
    analyses: dict[Timeframe, MTFTimeframeAnalysis] = {}
    daily = _daily_analysis(datasets[Timeframe.DAY_1], structures[Timeframe.DAY_1])
    h4 = _h4_analysis(datasets[Timeframe.HOUR_4], structures[Timeframe.HOUR_4], daily.bias)
    h1 = _h1_analysis(datasets[Timeframe.HOUR_1], structures[Timeframe.HOUR_1], h4.bias)
    m15 = _m15_analysis(datasets[Timeframe.MINUTE_15], structures[Timeframe.MINUTE_15], h1.bias)
    analyses.update({Timeframe.DAY_1: daily, Timeframe.HOUR_4: h4, Timeframe.HOUR_1: h1, Timeframe.MINUTE_15: m15})
    return MultiTimeframeResult(symbol=datasets[Timeframe.DAY_1].symbol, calculated_at=datetime.now(timezone.utc), timeframes=tuple(analyses[t] for t in REQUIRED_TIMEFRAMES), research=_research(daily, h4, h1, m15))
