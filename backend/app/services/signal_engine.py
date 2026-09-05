from __future__ import annotations

from datetime import datetime, timezone

from app.models.market import OHLCVDataset, Timeframe
from app.models.mtf import MTFBias
from app.models.signal import CryptoSignal, SignalComponent, SignalDirection
from app.services.market_structure import analyze_market_structure
from app.services.mtf_analysis import analyze_multi_timeframe
from app.services.technical_analysis import calculate_indicators

TIMEFRAME_WEIGHTS = {
    Timeframe.DAY_1: 0.35,
    Timeframe.HOUR_4: 0.30,
    Timeframe.HOUR_1: 0.20,
    Timeframe.MINUTE_15: 0.15,
}


def _sign(value: float | None, threshold: float = 0.0) -> float:
    if value is None:
        return 0.0
    if value > threshold:
        return 1.0
    if value < -threshold:
        return -1.0
    return 0.0


def _indicator_score(indicators: dict[str, float | str | None]) -> tuple[float, tuple[str, ...]]:
    contributions: list[tuple[float, float]] = []
    evidence: list[str] = []
    trend = indicators.get("trend")
    if trend == "BULLISH":
        contributions.append((1.0, 0.30))
        evidence.append("EMA trend stack is bullish.")
    elif trend == "BEARISH":
        contributions.append((-1.0, 0.30))
        evidence.append("EMA trend stack is bearish.")

    price = indicators.get("price")
    ema50 = indicators.get("ema50")
    ema200 = indicators.get("ema200")
    if isinstance(price, (int, float)) and isinstance(ema50, (int, float)):
        direction = 1.0 if price > ema50 else -1.0 if price < ema50 else 0.0
        contributions.append((direction, 0.15))
    if isinstance(price, (int, float)) and isinstance(ema200, (int, float)):
        direction = 1.0 if price > ema200 else -1.0 if price < ema200 else 0.0
        contributions.append((direction, 0.15))

    macd_hist = indicators.get("macd_histogram")
    if isinstance(macd_hist, (int, float)):
        direction = _sign(macd_hist)
        contributions.append((direction, 0.20))
        if direction:
            evidence.append("MACD histogram supports the directional move.")

    rsi = indicators.get("rsi14")
    if isinstance(rsi, (int, float)):
        if rsi >= 55:
            contributions.append((1.0, 0.10))
            evidence.append(f"RSI14 is constructive at {rsi:.1f}.")
        elif rsi <= 45:
            contributions.append((-1.0, 0.10))
            evidence.append(f"RSI14 is weak at {rsi:.1f}.")

    vwap = indicators.get("vwap")
    if isinstance(price, (int, float)) and isinstance(vwap, (int, float)):
        contributions.append((_sign(price - vwap), 0.10))

    total_weight = sum(weight for _, weight in contributions)
    if total_weight <= 0:
        return 0.0, ("Insufficient indicator evidence for a directional score.",)
    return max(-1.0, min(1.0, sum(value * weight for value, weight in contributions) / total_weight)), tuple(evidence)


def _smc_score(events) -> tuple[float, tuple[str, ...]]:
    directional: list[tuple[float, float]] = []
    evidence: list[str] = []
    latest_break = max(
        (event for event in events if event.type in {"BOS_BULLISH", "BOS_BEARISH", "CHOCH_BULLISH", "CHOCH_BEARISH"}),
        key=lambda event: event.time,
        default=None,
    )
    if latest_break is not None:
        bullish = latest_break.type.endswith("BULLISH")
        directional.append((1.0 if bullish else -1.0, 0.45 * max(latest_break.strength, 0.5)))
        evidence.append(f"Latest structure event is {latest_break.type}.")

    active_demand = [event for event in events if event.type in {"ORDER_BLOCK_BULLISH", "FVG_BULLISH"} and event.status.value == "ACTIVE"]
    active_supply = [event for event in events if event.type in {"ORDER_BLOCK_BEARISH", "FVG_BEARISH"} and event.status.value == "ACTIVE"]
    if active_demand and not active_supply:
        directional.append((1.0, 0.25))
        evidence.append("Active bullish OB/FVG demand is present.")
    elif active_supply and not active_demand:
        directional.append((-1.0, 0.25))
        evidence.append("Active bearish OB/FVG supply is present.")

    latest_sweep = max(
        (event for event in events if event.type in {"LIQUIDITY_SWEEP_HIGH", "LIQUIDITY_SWEEP_LOW"}),
        key=lambda event: event.time,
        default=None,
    )
    if latest_sweep is not None:
        bullish = latest_sweep.type == "LIQUIDITY_SWEEP_LOW"
        directional.append((1.0 if bullish else -1.0, 0.20 * max(latest_sweep.strength, 0.5)))
        evidence.append(f"Latest liquidity sweep is {latest_sweep.type}.")

    latest_inducement = max(
        (event for event in events if event.type in {"INDUCEMENT_BULLISH", "INDUCEMENT_BEARISH"}),
        key=lambda event: event.time,
        default=None,
    )
    if latest_inducement is not None:
        bullish = latest_inducement.type == "INDUCEMENT_BULLISH"
        directional.append((1.0 if bullish else -1.0, 0.10 * max(latest_inducement.strength, 0.5)))

    zone = max((event for event in events if event.type in {"PREMIUM", "DISCOUNT"}), key=lambda event: event.time, default=None)
    if zone is not None:
        directional.append((1.0 if zone.type == "DISCOUNT" else -1.0, 0.10))
        evidence.append(f"Price is in {zone.type.lower()} relative to the latest structure range.")

    total_weight = sum(weight for _, weight in directional)
    if total_weight <= 0:
        return 0.0, ("No directional SMC event is currently confirmed.",)
    return max(-1.0, min(1.0, sum(value * weight for value, weight in directional) / total_weight)), tuple(evidence)


def _signal_for_score(score: float) -> SignalDirection:
    if score >= 0.65:
        return SignalDirection.STRONG_BUY
    if score >= 0.25:
        return SignalDirection.BUY
    if score <= -0.65:
        return SignalDirection.STRONG_SELL
    if score <= -0.25:
        return SignalDirection.SELL
    return SignalDirection.NEUTRAL


def generate_crypto_signal(datasets: dict[Timeframe, OHLCVDataset]) -> CryptoSignal:
    required = tuple(TIMEFRAME_WEIGHTS)
    missing = [timeframe.value for timeframe in required if timeframe not in datasets]
    if missing:
        raise ValueError(f"Missing required signal timeframe(s): {', '.join(missing)}")

    components: list[SignalComponent] = []
    weighted_score = 0.0
    evidence: list[str] = []
    structures = {}
    for timeframe in required:
        dataset = datasets[timeframe]
        candles = list(dataset.completed_candles)
        if len(candles) < 30:
            raise ValueError(f"At least 30 completed candles are required for {timeframe.value} signal research.")
        indicators = calculate_indicators(candles)
        indicators["price"] = candles[-1].close
        structure = analyze_market_structure(dataset)
        structures[timeframe] = tuple(structure.events)
        indicator_score, indicator_evidence = _indicator_score(indicators)
        smc_score, smc_evidence = _smc_score(structure.events)
        combined = max(-1.0, min(1.0, 0.60 * indicator_score + 0.40 * smc_score))
        components.append(SignalComponent(
            timeframe=timeframe.value,
            indicator_score=indicator_score,
            smc_score=smc_score,
            combined_score=combined,
            evidence=indicator_evidence + smc_evidence,
        ))
        weighted_score += TIMEFRAME_WEIGHTS[timeframe] * combined
        evidence.extend(f"{timeframe.value}: {item}" for item in (indicator_evidence + smc_evidence))

    mtf = analyze_multi_timeframe(datasets, structures)
    if mtf.research.bias == MTFBias.BULLISH:
        weighted_score = 0.85 * weighted_score + 0.15 * mtf.research.confidence
        evidence.append(f"MTF strategy bias is bullish with {mtf.research.alignment_count}/4 timeframe alignment.")
    elif mtf.research.bias == MTFBias.BEARISH:
        weighted_score = 0.85 * weighted_score - 0.15 * mtf.research.confidence
        evidence.append(f"MTF strategy bias is bearish with {mtf.research.alignment_count}/4 timeframe alignment.")
    else:
        evidence.append("MTF strategy bias is neutral; no directional bonus applied.")

    weighted_score = max(-1.0, min(1.0, weighted_score))
    signal = _signal_for_score(weighted_score)
    confluence = min(1.0, 0.50 + 0.50 * abs(weighted_score))
    return CryptoSignal(
        symbol=datasets[Timeframe.DAY_1].symbol,
        signal=signal,
        score=weighted_score,
        confluence=confluence,
        price=datasets[Timeframe.MINUTE_15].completed_candles[-1].close,
        calculated_at=datetime.now(timezone.utc),
        latest_candle_timestamp=datasets[Timeframe.MINUTE_15].completed_candles[-1].timestamp,
        source=datasets[Timeframe.MINUTE_15].source,
        components=tuple(components),
        evidence=tuple(evidence[:12]),
        research_eligible=True,
    )
