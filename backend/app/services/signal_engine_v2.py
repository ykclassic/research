from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from app.models.market import OHLCVDataset, Timeframe
from app.models.mtf import MTFBias
from app.models.risk import RiskPolicy
from app.models.signal import CryptoSignal, RiskRewardStatus, SignalComponent, SignalDirection
from app.services.market_structure import analyze_market_structure
from app.services.mtf_analysis import analyze_multi_timeframe
from app.services.regime_detection import detect_regime
from app.services.technical_analysis import calculate_indicators
from app.services.market_session import build_session_state
from app.services.signal_feature_engine import build_feature_families, family_score
from app.services.trade_contract import build_trade_contract
from app.services.system_status import APPLICATION_VERSION

TIMEFRAME_WEIGHTS = {Timeframe.DAY_1: 0.35, Timeframe.HOUR_4: 0.30, Timeframe.HOUR_1: 0.20, Timeframe.MINUTE_15: 0.15}
SIGNAL_LEVEL_LOOKBACK = 50
SIGNAL_STOP_ATR_MULTIPLIER = RiskPolicy().stop_atr_multiplier
CONFIDENCE_BASE = 0.50
CONFIDENCE_SCORE_SCALE = 0.50
FEATURE_VERSION = "signal-features-v2"
SCORING_POLICY_VERSION = "family-weighted-v2"


@dataclass(frozen=True)
class CandidateTradeLevels:
    entry_price: float
    atr: float | None
    stop_distance: float | None
    stop_loss: float | None
    structural_target: float | None
    atr_minimum_target: float | None
    take_profit: float | None
    risk_reward: float | None
    risk_reward_reason: str | None
    reasons: tuple[str, ...] = ()


def _signal_for_score(score: float) -> SignalDirection:
    if score >= 0.65: return SignalDirection.STRONG_BUY
    if score >= 0.25: return SignalDirection.BUY
    if score <= -0.65: return SignalDirection.STRONG_SELL
    if score <= -0.25: return SignalDirection.SELL
    return SignalDirection.NEUTRAL


def _confidence_from_score(score: float) -> float:
    return min(1.0, CONFIDENCE_BASE + CONFIDENCE_SCORE_SCALE * abs(score))


def _structural_levels(candles: list[Any], price: float) -> tuple[list[float], list[float]]:
    window = candles[-SIGNAL_LEVEL_LOOKBACK:]
    supports, resistances = [], []
    for i in range(2, len(window) - 2):
        low, high = float(window[i].low), float(window[i].high)
        if all(float(window[i-j].low) > low and float(window[i+j].low) > low for j in (1,2)) and low < price: supports.append(low)
        if all(float(window[i-j].high) < high and float(window[i+j].high) < high for j in (1,2)) and high > price: resistances.append(high)
    return sorted(set(supports), reverse=True), sorted(set(resistances))


def _smc_score(events) -> tuple[float, tuple[str, ...]]:
    parts, evidence = [], []
    breaks = [e for e in events if e.type in {"BOS_BULLISH","BOS_BEARISH","CHOCH_BULLISH","CHOCH_BEARISH"}]
    if breaks:
        e = max(breaks, key=lambda x: x.time)
        parts.append((1.0 if e.type.endswith("BULLISH") else -1.0, 0.45 * max(float(e.strength), 0.5)))
        evidence.append(f"Latest structure event is {e.type}.")
    demand = [e for e in events if e.type in {"ORDER_BLOCK_BULLISH","FVG_BULLISH"} and e.status.value == "ACTIVE"]
    supply = [e for e in events if e.type in {"ORDER_BLOCK_BEARISH","FVG_BEARISH"} and e.status.value == "ACTIVE"]
    if demand and not supply: parts.append((1.0, 0.25)); evidence.append("Active bullish OB/FVG demand is present.")
    if supply and not demand: parts.append((-1.0, 0.25)); evidence.append("Active bearish OB/FVG supply is present.")
    sweeps = [e for e in events if e.type in {"LIQUIDITY_SWEEP_HIGH","LIQUIDITY_SWEEP_LOW"}]
    if sweeps:
        e = max(sweeps, key=lambda x: x.time); parts.append((1.0 if e.type.endswith("LOW") else -1.0, 0.20 * max(float(e.strength), 0.5))); evidence.append(f"Latest liquidity sweep is {e.type}.")
    inducements = [e for e in events if e.type in {"INDUCEMENT_BULLISH","INDUCEMENT_BEARISH"}]
    if inducements:
        e = max(inducements, key=lambda x: x.time); parts.append((1.0 if e.type.endswith("BULLISH") else -1.0, 0.10 * max(float(e.strength), 0.5)))
    zones = [e for e in events if e.type in {"PREMIUM","DISCOUNT"}]
    if zones:
        e = max(zones, key=lambda x: x.time); parts.append((1.0 if e.type == "DISCOUNT" else -1.0, 0.10)); evidence.append(f"Price is in {e.type.lower()} relative to the latest structure range.")
    total = sum(weight for _, weight in parts)
    return ((sum(value * weight for value, weight in parts) / total) if total else 0.0), tuple(evidence)


def _candidate_trade_levels(signal: SignalDirection, entry_price: float, atr: float | None, candles: list[Any], minimum_risk_reward: float, stop_atr_multiplier: float = SIGNAL_STOP_ATR_MULTIPLIER) -> CandidateTradeLevels:
    if signal == SignalDirection.NEUTRAL:
        return CandidateTradeLevels(entry_price, atr, None, None, None, None, None, None, "Neutral direction has no trade contract.", ("Neutral direction; no trade levels generated.",))
    if atr is None or not isfinite(float(atr)) or float(atr) <= 0:
        return CandidateTradeLevels(entry_price, atr, None, None, None, None, None, None, "Positive finite ATR is required.", ("Positive finite ATR is required.",))
    stop_distance = float(atr) * stop_atr_multiplier
    buy = signal in {SignalDirection.BUY, SignalDirection.STRONG_BUY}
    stop = entry_price - stop_distance if buy else entry_price + stop_distance
    minimum_target = entry_price + stop_distance * minimum_risk_reward if buy else entry_price - stop_distance * minimum_risk_reward
    supports, resistances = _structural_levels(candles, entry_price)
    targets = resistances if buy else supports
    valid = [t for t in targets if (t > entry_price if buy else t < entry_price)]
    if not valid:
        return CandidateTradeLevels(entry_price, float(atr), stop_distance, stop, None, minimum_target, None, None, "No validated structural target exists beyond entry.", ("No validated structural target exists beyond entry.",))
    risk = abs(entry_price - stop)
    selected = next((t for t in valid if abs(t-entry_price)/risk >= minimum_risk_reward), None)
    nearest = valid[0]
    rr = abs((selected or nearest)-entry_price) / risk if risk else 0.0
    if selected is None:
        return CandidateTradeLevels(entry_price, float(atr), stop_distance, stop, nearest, minimum_target, None, rr, f"No structural target satisfies {minimum_risk_reward:.2f}:1 minimum RR.", (f"Nearest structural target provides {rr:.2f}:1 RR.",))
    return CandidateTradeLevels(entry_price, float(atr), stop_distance, stop, selected, minimum_target, selected, rr, None, ())


def _qualify(signal, strength, risk_reward, mtf_bias, mtf_alignment, structure_score, preferences):
    minimum = float(preferences.get("minimum_confidence", 0.0))
    minimum_rr = float(preferences.get("minimum_risk_reward", 0.0))
    preferred = set(preferences.get("preferred_signal_types") or ["BUY","SELL","NEUTRAL"])
    direction = "BUY" if signal in {SignalDirection.BUY, SignalDirection.STRONG_BUY} else "SELL" if signal in {SignalDirection.SELL, SignalDirection.STRONG_SELL} else "NEUTRAL"
    reasons = []
    if strength < minimum: reasons.append(f"Signal strength {strength:.1%} is below the {minimum:.1%} minimum.")
    if direction not in preferred: reasons.append(f"{direction} is not an enabled preferred signal type.")
    if direction != "NEUTRAL" and (risk_reward is None or risk_reward < minimum_rr): reasons.append(f"Risk/reward does not meet the {minimum_rr:.2f}:1 minimum.")
    if preferences.get("require_multi_timeframe_confirmation") and direction != "NEUTRAL":
        aligned = (direction == "BUY" and mtf_bias == MTFBias.BULLISH) or (direction == "SELL" and mtf_bias == MTFBias.BEARISH)
        if not aligned or mtf_alignment < 3: reasons.append("Multi-timeframe confirmation is required but is not sufficiently aligned.")
    if preferences.get("require_market_structure_confirmation") and direction != "NEUTRAL":
        if not ((direction == "BUY" and structure_score > 0) or (direction == "SELL" and structure_score < 0)): reasons.append("Market-structure confirmation is required but is not aligned.")
    return not reasons, tuple(reasons)


def generate_crypto_signal(datasets: dict[Timeframe, OHLCVDataset], signal_preferences: dict[str, Any] | None = None, *, selected_timeframes: tuple[Timeframe, ...] | None = None, asset_class: str = "crypto") -> CryptoSignal:
    preferences = signal_preferences or {"minimum_confidence":0.0,"preferred_signal_types":["BUY","SELL","NEUTRAL"],"minimum_risk_reward":0.0,"require_multi_timeframe_confirmation":False,"require_market_structure_confirmation":False}
    selected = tuple(selected_timeframes or TIMEFRAME_WEIGHTS)
    if any(tf not in TIMEFRAME_WEIGHTS for tf in selected): raise ValueError("Unsupported signal timeframe selected.")
    missing = [tf.value for tf in TIMEFRAME_WEIGHTS if tf not in datasets]
    if missing: raise ValueError(f"Missing required signal timeframe(s): {', '.join(missing)}")
    components, structures, evidence, family_values = [], {}, [], {}
    scores = []
    for timeframe in TIMEFRAME_WEIGHTS:
        candles = list(datasets[timeframe].completed_candles)
        if len(candles) < 30: raise ValueError(f"At least 30 completed candles are required for {timeframe.value} signal research.")
        indicators = calculate_indicators(candles); indicators["price"] = candles[-1].close
        structure = analyze_market_structure(datasets[timeframe]); structures[timeframe] = tuple(structure.events)
        smc, smc_evidence = _smc_score(structure.events)
        families = build_feature_families(indicators, price=candles[-1].close)
        family = family_score(families)
        combined = max(-1.0, min(1.0, 0.75 * family + 0.25 * smc))
        scores.append((timeframe, combined))
        for f in families: family_values[f.name] = family_values.get(f.name, 0.0) + f.value / len(TIMEFRAME_WEIGHTS)
        family_evidence = tuple(item for f in families for item in f.evidence)
        components.append(SignalComponent(timeframe=timeframe.value, indicator_score=family, smc_score=smc, combined_score=combined, evidence=family_evidence + smc_evidence))
        evidence.extend(f"{timeframe.value}: {x}" for x in family_evidence + smc_evidence)
    selected_total = sum(TIMEFRAME_WEIGHTS[tf] for tf in selected)
    weighted = sum((TIMEFRAME_WEIGHTS[tf]/selected_total)*score for tf, score in scores if tf in selected)
    mtf = analyze_multi_timeframe(datasets, structures)
    if mtf.research.bias == MTFBias.BULLISH: weighted = 0.85*weighted + 0.15*mtf.research.confidence
    elif mtf.research.bias == MTFBias.BEARISH: weighted = 0.85*weighted - 0.15*mtf.research.confidence
    weighted = max(-1.0, min(1.0, weighted)); signal = _signal_for_score(weighted); strength = _confidence_from_score(weighted)
    m15 = datasets[Timeframe.MINUTE_15]; candles = list(m15.completed_candles); entry = candles[-1].close
    indicators = calculate_indicators(candles); atr = indicators.get("atr14"); minimum_rr = float(preferences.get("minimum_risk_reward",0.0))
    levels = _candidate_trade_levels(signal, entry, float(atr) if isinstance(atr,(int,float)) else None, candles, minimum_rr)
    structure_score = sum(c.smc_score for c in components)/len(components)
    qualified, qualification_reasons = _qualify(signal, strength, levels.risk_reward, mtf.research.bias, mtf.research.alignment_count, structure_score, preferences)
    direction = "BUY" if signal in {SignalDirection.BUY,SignalDirection.STRONG_BUY} else "SELL" if signal in {SignalDirection.SELL,SignalDirection.STRONG_SELL} else "NEUTRAL"
    contract = None
    if levels.take_profit is not None and levels.stop_distance is not None:
        contract = build_trade_contract(direction=direction, entry_price=entry, stop_distance=levels.stop_distance, target_price=levels.take_profit, spread_bps=float(preferences.get("spread_bps",0.0)), slippage_bps=float(preferences.get("slippage_bps",0.0)), fee_bps=float(preferences.get("fee_bps",0.0)))
    try: regime = detect_regime(m15)
    except ValueError: regime = None
    events = sorted(structures[Timeframe.MINUTE_15], key=lambda e:e.time); recent = events[-6:]
    sweep = next((e for e in reversed(events) if e.type.startswith("LIQUIDITY_SWEEP_")), None)
    session = build_session_state(asset_class=asset_class, now=candles[-1].timestamp, market_open=True, dataset=m15, symbol=m15.symbol)
    reasons = tuple(dict.fromkeys((*levels.reasons,*qualification_reasons,*(() if contract is None else contract.reasons))))
    probability = None  # populated only by a separately trained/calibrated model; never inferred from score.
    return CryptoSignal(symbol=datasets[Timeframe.DAY_1].symbol, signal=signal, score=weighted, signal_strength=strength, confidence=strength, calibrated_probability=probability, confluence=min(1.0, len([f for f,v in family_values.items() if abs(v) >= 0.15])/5), confluence_families=tuple(sorted(f for f,v in family_values.items() if abs(v) >= 0.15)), expected_value_r=(probability*levels.risk_reward-(1-probability) if probability is not None and levels.risk_reward is not None else None), risk_reward=levels.risk_reward, risk_reward_status=RiskRewardStatus.AVAILABLE if levels.risk_reward is not None and levels.take_profit is not None else RiskRewardStatus.UNAVAILABLE, risk_reward_reason=levels.risk_reward_reason, structural_target=levels.structural_target, atr_minimum_target=levels.atr_minimum_target, price=entry, entry_price=entry, stop_loss=contract.stop_loss if contract else levels.stop_loss, take_profit=contract.take_profit if contract else levels.take_profit, atr=levels.atr, stop_distance=levels.stop_distance, position_size=contract.position_size if contract else None, expected_cost=contract.expected_cost if contract else 0.0, expected_slippage=contract.expected_slippage if contract else 0.0, expected_spread=contract.expected_spread if contract else 0.0, calculated_at=datetime.now(timezone.utc), latest_candle_timestamp=candles[-1].timestamp, source=m15.source, components=tuple(components), evidence=tuple(evidence[:30]), research_eligible=qualified, qualification_reasons=reasons, minimum_confidence=float(preferences.get("minimum_confidence",0.0)), minimum_risk_reward=minimum_rr, qualification_status="QUALIFIED" if qualified else "REJECTED", mtf_bias=mtf.research.bias.value, mtf_alignment=mtf.research.alignment_count, regime=regime.regime.value if regime else "UNKNOWN", regime_confidence=regime.confidence if regime else 0.0, market_structure=", ".join(e.type for e in recent) or "NONE", liquidity_conditions=("SWEEP_LOW" if sweep and sweep.type.endswith("LOW") else "SWEEP_HIGH" if sweep else "NO_CONFIRMED_SWEEP"), momentum=float(indicators.get("macd_histogram")) if isinstance(indicators.get("macd_histogram"),(int,float)) else None, volatility=(float(atr)/entry if isinstance(atr,(int,float)) and entry else None), session=session.label, strategy="signal_engine_v2", signal_engine_version=APPLICATION_VERSION, feature_version=FEATURE_VERSION, scoring_policy_version=SCORING_POLICY_VERSION, risk_policy_version=RiskPolicy().policy_version, execution_model_version="execution-v1", structural_conditions={"recent_events":[e.type for e in recent],"mtf_primary_setup":mtf.research.primary_setup,"mtf_conclusion":mtf.research.conclusion,"regime_rule":regime.rule_id if regime else "INSUFFICIENT_HISTORY"}, feature_families={k:round(v,6) for k,v in family_values.items()}, replay_candles=tuple({"timestamp":c.timestamp,"open":c.open,"high":c.high,"low":c.low,"close":c.close,"volume":float(c.volume or 0.0),"timeframe":c.timeframe.value,"source":c.source} for c in candles[-120:]))
