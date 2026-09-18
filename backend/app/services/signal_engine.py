from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from app.models.market import OHLCVDataset, Timeframe
from app.models.mtf import MTFBias
from app.models.risk import RiskPolicy
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

SIGNAL_LEVEL_LOOKBACK = 50
SIGNAL_STOP_ATR_MULTIPLIER = RiskPolicy().stop_atr_multiplier


@dataclass(frozen=True)
class CandidateTradeLevels:
    entry_price: float
    atr: float | None
    stop_distance: float | None
    stop_loss: float | None
    structural_target: float | None
    atr_minimum_target: float | None
    take_profit: float | None
    risk_reward: float
    reasons: tuple[str, ...] = ()


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
        contributions.append((1.0 if price > ema50 else -1.0 if price < ema50 else 0.0, 0.15))
    if isinstance(price, (int, float)) and isinstance(ema200, (int, float)):
        contributions.append((1.0 if price > ema200 else -1.0 if price < ema200 else 0.0, 0.15))

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


def _structural_levels(candles: list[Any], price: float) -> tuple[float | None, float | None]:
    window = candles[-SIGNAL_LEVEL_LOOKBACK:]
    supports = [float(candle.low) for candle in window if candle.low < price]
    resistances = [float(candle.high) for candle in window if candle.high > price]
    return (max(supports) if supports else None, min(resistances) if resistances else None)


def _candidate_trade_levels(
    signal: SignalDirection,
    entry_price: float,
    atr: float | None,
    candles: list[Any],
    minimum_risk_reward: float,
    stop_atr_multiplier: float = SIGNAL_STOP_ATR_MULTIPLIER,
) -> CandidateTradeLevels:
    if signal == SignalDirection.NEUTRAL:
        return CandidateTradeLevels(
            entry_price=entry_price, atr=atr, stop_distance=None, stop_loss=None,
            structural_target=None, atr_minimum_target=None, take_profit=None,
            risk_reward=0.0,
            reasons=("Directional bias is neutral; no trade levels are generated.",),
        )

    if not isfinite(entry_price) or entry_price <= 0 or atr is None or not isfinite(float(atr)) or float(atr) <= 0:
        return CandidateTradeLevels(
            entry_price=entry_price, atr=atr, stop_distance=None, stop_loss=None,
            structural_target=None, atr_minimum_target=None, take_profit=None,
            risk_reward=0.0,
            reasons=("A positive finite ATR14 is required for candidate trade levels.",),
        )

    atr_value = float(atr)
    stop_distance = atr_value * stop_atr_multiplier
    if stop_distance <= 0 or not isfinite(stop_distance):
        return CandidateTradeLevels(
            entry_price=entry_price, atr=atr_value, stop_distance=None, stop_loss=None,
            structural_target=None, atr_minimum_target=None, take_profit=None,
            risk_reward=0.0,
            reasons=("ATR-based stop distance is invalid.",),
        )

    support, resistance = _structural_levels(candles, entry_price)
    direction_is_buy = signal in {SignalDirection.BUY, SignalDirection.STRONG_BUY}
    structural_target = resistance if direction_is_buy else support
    stop_loss = entry_price - stop_distance if direction_is_buy else entry_price + stop_distance
    atr_minimum_target = (
        entry_price + stop_distance * minimum_risk_reward
        if direction_is_buy
        else entry_price - stop_distance * minimum_risk_reward
    )
    reasons: list[str] = []

    if stop_loss <= 0:
        reasons.append("ATR-based candidate stop is non-positive.")

    if structural_target is None:
        side = "resistance" if direction_is_buy else "support"
        reasons.append(f"No structural {side} level exists beyond the entry.")
        return CandidateTradeLevels(
            entry_price=entry_price, atr=atr_value, stop_distance=stop_distance,
            stop_loss=stop_loss, structural_target=None,
            atr_minimum_target=atr_minimum_target, take_profit=None,
            risk_reward=0.0, reasons=tuple(reasons),
        )

    if direction_is_buy:
        if structural_target <= entry_price:
            reasons.append("Structural resistance is not above the BUY entry.")
        elif structural_target < atr_minimum_target:
            reasons.append(
                f"Structural target {structural_target:.8f} conflicts with the "
                f"ATR-derived minimum target {atr_minimum_target:.8f}."
            )
    else:
        if structural_target >= entry_price:
            reasons.append("Structural support is not below the SELL entry.")
        elif structural_target > atr_minimum_target:
            reasons.append(
                f"Structural target {structural_target:.8f} conflicts with the "
                f"ATR-derived minimum target {atr_minimum_target:.8f}."
            )

    if (
        (direction_is_buy and structural_target <= entry_price)
        or (not direction_is_buy and structural_target >= entry_price)
    ):
        return CandidateTradeLevels(
            entry_price=entry_price, atr=atr_value, stop_distance=stop_distance,
            stop_loss=stop_loss, structural_target=structural_target,
            atr_minimum_target=atr_minimum_target, take_profit=None,
            risk_reward=0.0, reasons=tuple(reasons),
        )

    take_profit = structural_target
    risk_reward = abs(take_profit - entry_price) / stop_distance
    if risk_reward < minimum_risk_reward:
        reasons.append(f"Risk/reward {risk_reward:.2f} is below the {minimum_risk_reward:.2f} minimum.")

    return CandidateTradeLevels(
        entry_price=entry_price, atr=atr_value, stop_distance=stop_distance,
        stop_loss=stop_loss, structural_target=structural_target,
        atr_minimum_target=atr_minimum_target, take_profit=take_profit,
        risk_reward=max(0.0, risk_reward), reasons=tuple(reasons),
    )


def _preferred_direction(signal: SignalDirection) -> str:
    if signal in {SignalDirection.BUY, SignalDirection.STRONG_BUY}:
        return "BUY"
    if signal in {SignalDirection.SELL, SignalDirection.STRONG_SELL}:
        return "SELL"
    return "NEUTRAL"


def _qualify(
    signal: SignalDirection,
    confidence: float,
    risk_reward: float,
    mtf_bias: MTFBias,
    mtf_alignment: int,
    structure_score: float,
    preferences: dict[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    minimum_confidence = float(preferences.get("minimum_confidence", 0.0))
    minimum_rr = float(preferences.get("minimum_risk_reward", 0.0))
    preferred = set(preferences.get("preferred_signal_types") or ["BUY", "SELL", "NEUTRAL"])
    direction = _preferred_direction(signal)
    reasons: list[str] = []
    if confidence < minimum_confidence:
        reasons.append(f"Confidence {confidence:.1%} is below the {minimum_confidence:.1%} minimum.")
    if direction not in preferred:
        reasons.append(f"{direction} is not an enabled preferred signal type.")
    if direction != "NEUTRAL" and risk_reward < minimum_rr:
        reasons.append(f"Risk/reward {risk_reward:.2f} is below the {minimum_rr:.2f} minimum.")
    if preferences.get("require_multi_timeframe_confirmation") and direction != "NEUTRAL":
        aligned = (direction == "BUY" and mtf_bias == MTFBias.BULLISH) or (direction == "SELL" and mtf_bias == MTFBias.BEARISH)
        if not aligned or mtf_alignment < 3:
            reasons.append("Multi-timeframe confirmation is required but is not sufficiently aligned.")
    if preferences.get("require_market_structure_confirmation") and direction != "NEUTRAL":
        structure_aligned = (direction == "BUY" and structure_score > 0) or (direction == "SELL" and structure_score < 0)
        if not structure_aligned:
            reasons.append("Market-structure confirmation is required but is not aligned with the signal.")
    return not reasons, tuple(reasons)


def generate_crypto_signal(
    datasets: dict[Timeframe, OHLCVDataset],
    signal_preferences: dict[str, Any] | None = None,
) -> CryptoSignal:
    preferences = signal_preferences or {
        "minimum_confidence": 0.0,
        "preferred_signal_types": ["BUY", "SELL", "NEUTRAL"],
        "minimum_risk_reward": 0.0,
        "require_multi_timeframe_confirmation": False,
        "require_market_structure_confirmation": False,
    }
    required = tuple(TIMEFRAME_WEIGHTS)
    missing = [timeframe.value for timeframe in required if timeframe not in datasets]
    if missing:
        raise ValueError(f"Missing required signal timeframe(s): {', '.join(missing)}")

    components: list[SignalComponent] = []
    weighted_score = 0.0
    evidence: list[str] = []
    structures = {}
    smc_scores: list[float] = []

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
        smc_scores.append(smc_score)
        combined = max(-1.0, min(1.0, 0.60 * indicator_score + 0.40 * smc_score))
        components.append(
            SignalComponent(
                timeframe=timeframe.value,
                indicator_score=indicator_score,
                smc_score=smc_score,
                combined_score=combined,
                evidence=indicator_evidence + smc_evidence,
            )
        )
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
    confidence = min(1.0, 0.50 + 0.50 * abs(weighted_score))
    entry_price = datasets[Timeframe.MINUTE_15].completed_candles[-1].close
    m15_indicators = calculate_indicators(list(datasets[Timeframe.MINUTE_15].completed_candles))
    atr = m15_indicators.get("atr14")
    minimum_rr = float(preferences.get("minimum_risk_reward", 0.0))
    levels = _candidate_trade_levels(
        signal,
        entry_price,
        float(atr) if isinstance(atr, (int, float)) else None,
        list(datasets[Timeframe.MINUTE_15].completed_candles),
        minimum_rr,
    )
    structure_score = sum(smc_scores) / len(smc_scores) if smc_scores else 0.0

    evidence.append(f"Directional bias: {_preferred_direction(signal)}.")
    if levels.stop_loss is not None:
        evidence.append(f"ATR candidate stop: {levels.stop_loss:.8f} ({SIGNAL_STOP_ATR_MULTIPLIER:.2f}x ATR14).")
    if levels.structural_target is not None:
        evidence.append(f"Structural target: {levels.structural_target:.8f}.")
    if levels.atr_minimum_target is not None:
        evidence.append(f"ATR-derived minimum target for {minimum_rr:.2f}:1 RR: {levels.atr_minimum_target:.8f}.")
    if levels.take_profit is not None:
        evidence.append(
            f"Candidate levels: entry {levels.entry_price:.8f}, stop {levels.stop_loss:.8f}, "
            f"target {levels.take_profit:.8f}, RR {levels.risk_reward:.2f}:1."
        )
    evidence.extend(levels.reasons)

    qualified, qualification_reasons = _qualify(
        signal, confidence, levels.risk_reward, mtf.research.bias,
        mtf.research.alignment_count, structure_score, preferences,
    )
    all_reasons = tuple(dict.fromkeys((*levels.reasons, *qualification_reasons)))

    return CryptoSignal(
        symbol=datasets[Timeframe.DAY_1].symbol,
        signal=signal,
        score=weighted_score,
        confidence=confidence,
        confluence=confidence,
        risk_reward=levels.risk_reward,
        price=entry_price,
        entry_price=levels.entry_price,
        stop_loss=levels.stop_loss,
        take_profit=levels.take_profit,
        atr=levels.atr,
        calculated_at=datetime.now(timezone.utc),
        latest_candle_timestamp=datasets[Timeframe.MINUTE_15].completed_candles[-1].timestamp,
        source=datasets[Timeframe.MINUTE_15].source,
        components=tuple(components),
        evidence=tuple(evidence[:20]),
        research_eligible=qualified,
        qualification_reasons=all_reasons,
        qualification_status="QUALIFIED" if qualified else "REJECTED",
    )
