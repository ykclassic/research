from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from app.models.enhanced_signal import EnhancedSignalChecks
from app.models.market import OHLCVDataset, Timeframe
from app.models.risk import RiskPolicy
from app.models.signal import CryptoSignal, RiskRewardStatus, SignalComponent, SignalDirection
from app.services.market_session import build_session_state
from app.services.market_structure import analyze_market_structure
from app.services.mtf_analysis import analyze_multi_timeframe
from app.services.regime_detection import detect_regime
from app.services.system_status import APPLICATION_VERSION
from app.services.trade_contract import build_trade_contract
from app.symbols import normalize_symbol

METHODOLOGY_VERSION = "enhanced-smc-v1"
HTF_TIMEFRAMES = (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1)
ENTRY_TIMEFRAMES = (Timeframe.MINUTE_15, Timeframe.MINUTE_5)
MINIMUM_RR = 2.0
POI_MAX_ATR_DISTANCE = 0.75
STOP_ATR_BUFFER = 0.10
RECENT_EVENT_BARS = 12


@dataclass(frozen=True)
class _Setup:
    direction: SignalDirection
    poi: Any | None
    sweep: Any | None
    displacement: Any | None
    micro_break: Any | None
    opposing_target: float | None
    stop_loss: float | None
    risk_reward: float | None
    path_clear: bool
    reasons: tuple[str, ...]


def _direction_from_break(events: list[Any]) -> str | None:
    breaks = [e for e in events if e.type in {
        "BOS_BULLISH", "BOS_BEARISH", "CHOCH_BULLISH", "CHOCH_BEARISH"
    }]
    if not breaks:
        return None
    latest = max(breaks, key=lambda e: e.time)
    return "BULLISH" if latest.type.endswith("BULLISH") else "BEARISH"


def _direction_from_structure(events: list[Any]) -> str | None:
    direction = _direction_from_break(events)
    if direction:
        return direction
    recent = sorted(
        [e for e in events if e.type in {"HIGHER_HIGH", "HIGHER_LOW", "LOWER_HIGH", "LOWER_LOW"}],
        key=lambda e: e.time,
    )[-4:]
    bullish = sum(e.type in {"HIGHER_HIGH", "HIGHER_LOW"} for e in recent)
    bearish = sum(e.type in {"LOWER_HIGH", "LOWER_LOW"} for e in recent)
    if bullish > bearish:
        return "BULLISH"
    if bearish > bullish:
        return "BEARISH"
    return None


def _latest(events: list[Any], *types: str) -> Any | None:
    matches = [e for e in events if e.type in types]
    return max(matches, key=lambda e: e.time) if matches else None


def _after(events: list[Any], anchor: Any | None, *types: str) -> Any | None:
    if anchor is None:
        return None
    matches = [e for e in events if e.type in types and e.time > anchor.time]
    return max(matches, key=lambda e: e.time) if matches else None


def _active_poi(events: list[Any], direction: str, price: float, atr: float) -> Any | None:
    types = {"ORDER_BLOCK_BULLISH", "FVG_BULLISH"} if direction == "BULLISH" else {"ORDER_BLOCK_BEARISH", "FVG_BEARISH"}
    candidates = [
        e for e in events
        if e.type in types and e.status.value == "ACTIVE"
        and abs(price - float(e.price)) <= POI_MAX_ATR_DISTANCE * atr
    ]
    return min(candidates, key=lambda e: abs(price - float(e.price))) if candidates else None


def _premium_discount_valid(events: list[Any], direction: str) -> bool:
    latest = _latest(events, "PREMIUM", "DISCOUNT")
    if latest is None:
        return False
    return latest.type == ("DISCOUNT" if direction == "BULLISH" else "PREMIUM")


def _liquidity_target(
    events: list[Any],
    direction: str,
    entry: float,
    risk_distance: float,
) -> float | None:
    if direction == "BULLISH":
        candidates = [
            float(e.price) for e in events
            if e.type in {"LIQUIDITY_POOL_HIGH", "EQUAL_HIGH", "SWING_HIGH", "HIGHER_HIGH"}
            and float(e.price) > entry
        ]
    else:
        candidates = [
            float(e.price) for e in events
            if e.type in {"LIQUIDITY_POOL_LOW", "EQUAL_LOW", "SWING_LOW", "LOWER_LOW"}
            and float(e.price) < entry
        ]
    candidates = sorted(set(candidates))
    for target in candidates:
        if risk_distance > 0 and abs(target - entry) / risk_distance >= MINIMUM_RR:
            return target
    return None


def _path_clear(
    events: list[Any],
    direction: str,
    entry: float,
    target: float,
) -> bool:
    opposing = {
        "BULLISH": {"ORDER_BLOCK_BEARISH", "FVG_BEARISH", "LIQUIDITY_POOL_HIGH"},
        "BEARISH": {"ORDER_BLOCK_BULLISH", "FVG_BULLISH", "LIQUIDITY_POOL_LOW"},
    }[direction]
    for event in events:
        if event.type not in opposing or event.status.value not in {"ACTIVE", "CONFIRMED"}:
            continue
        level = float(event.price)
        if direction == "BULLISH" and entry < level < target:
            return False
        if direction == "BEARISH" and target < level < entry:
            return False
    return True


def _build_setup(
    events_15m: list[Any],
    events_5m: list[Any],
    *,
    price: float,
    atr: float,
    htf_direction: str,
) -> _Setup:
    direction = SignalDirection.STRONG_BUY if htf_direction == "BULLISH" else SignalDirection.STRONG_SELL
    poi = _active_poi(events_15m, htf_direction, price, atr)
    sweep_type = "LIQUIDITY_SWEEP_LOW" if htf_direction == "BULLISH" else "LIQUIDITY_SWEEP_HIGH"
    displacement_type = "DISPLACEMENT_BULLISH" if htf_direction == "BULLISH" else "DISPLACEMENT_BEARISH"
    break_types = ("BOS_BULLISH", "CHOCH_BULLISH") if htf_direction == "BULLISH" else ("BOS_BEARISH", "CHOCH_BEARISH")

    sweep = _latest(events_5m, sweep_type)
    displacement = _after(events_5m, sweep, displacement_type)
    micro_break = _after(events_5m, displacement, *break_types)

    reasons: list[str] = []
    if poi is None:
        reasons.append("Current price is not tapping an active directional OB/FVG on 15m.")
    if sweep is None:
        reasons.append("No recent opposing liquidity sweep is confirmed on 5m.")
    if displacement is None:
        reasons.append("No directional displacement is confirmed after the sweep.")
    if micro_break is None:
        reasons.append("No post-sweep micro structure break is confirmed.")
    if not _premium_discount_valid(events_15m, htf_direction):
        reasons.append("Price is not in the required premium/discount quadrant.")

    if poi is None or sweep is None or displacement is None or micro_break is None:
        return _Setup(direction, poi, sweep, displacement, micro_break, None, None, None, False, tuple(reasons))

    poi_invalidation = float(poi.invalidation) if poi.invalidation is not None else float(poi.price)
    sweep_extreme = float(sweep.invalidation) if sweep.invalidation is not None else float(sweep.price)
    if htf_direction == "BULLISH":
        stop = min(poi_invalidation, sweep_extreme) - STOP_ATR_BUFFER * atr
    else:
        stop = max(poi_invalidation, sweep_extreme) + STOP_ATR_BUFFER * atr

    risk = abs(price - stop)
    target = _liquidity_target(events_15m + events_5m, htf_direction, price, risk)
    path_clear = target is not None and _path_clear(events_15m + events_5m, htf_direction, price, target)
    rr = abs(target - price) / risk if target is not None and risk > 0 else None

    if target is None:
        reasons.append("No opposing liquidity target provides the required 2.00:1 RR.")
    if target is not None and not path_clear:
        reasons.append("An opposing active structure/liquidity zone blocks the path to target.")
    if rr is not None and rr < MINIMUM_RR:
        reasons.append(f"Risk/reward {rr:.2f}:1 is below the 2.00:1 floor.")

    return _Setup(direction, poi, sweep, displacement, micro_break, target, stop, rr, path_clear, tuple(reasons))


def _quality_score(checks: dict[str, bool], sweep: Any | None, displacement: Any | None, micro_break: Any | None) -> float:
    weights = {
        "htf_aligned": 0.20,
        "setup_structure_aligned": 0.10,
        "valid_poi": 0.15,
        "premium_discount_valid": 0.10,
        "liquidity_sweep_confirmed": 0.10,
        "displacement_confirmed": 0.10,
        "micro_structure_confirmed": 0.10,
        "entry_location_valid": 0.05,
        "opposing_liquidity_target": 0.05,
        "path_to_target_clear": 0.025,
        "minimum_rr_met": 0.025,
    }
    base = sum(weight for key, weight in weights.items() if checks.get(key))
    strength_bonus = 0.0
    if sweep is not None:
        strength_bonus += 0.025 * float(sweep.strength)
    if displacement is not None:
        strength_bonus += 0.025 * float(displacement.strength)
    if micro_break is not None:
        strength_bonus += 0.025 * float(micro_break.strength)
    return min(1.0, base + strength_bonus)


def generate_enhanced_signal(
    datasets: dict[Timeframe, OHLCVDataset],
    *,
    asset_class: str,
    account_risk_per_trade: float | None = None,
    news_filter_passed: bool = False,
) -> tuple[CryptoSignal, EnhancedSignalChecks]:
    required = (*HTF_TIMEFRAMES, *ENTRY_TIMEFRAMES)
    missing = [tf.value for tf in required if tf not in datasets]
    if missing:
        raise ValueError(f"Missing required enhanced-signal timeframe(s): {', '.join(missing)}")

    structures = {tf: analyze_market_structure(datasets[tf]) for tf in required}
    events = {tf: list(structures[tf].events) for tf in required}

    htf_biases = [_direction_from_structure(events[tf]) for tf in HTF_TIMEFRAMES]
    htf_direction = htf_biases[0] if htf_biases[0] and all(x == htf_biases[0] for x in htf_biases) else None

    m15 = datasets[Timeframe.MINUTE_15]
    m5 = datasets[Timeframe.MINUTE_5]
    price = float(m5.completed_candles[-1].close)
    atr = float(calculate_atr(m5))
    session = build_session_state(
        asset_class=asset_class,
        now=m5.completed_candles[-1].timestamp,
        market_open=True,
        dataset=m5,
        symbol=m5.symbol,
    )
    session_valid = session.status == "OPEN" and (
        asset_class != "forex" or session.phase in {"LONDON", "NEW_YORK", "OVERLAP"}
    )
    volatility_valid = session.volatility_state not in {"VERY_LOW", "UNKNOWN"}

    mtf = analyze_multi_timeframe(
        {tf: datasets[tf] for tf in HTF_TIMEFRAMES + (Timeframe.MINUTE_15,)},
        {tf: tuple(events[tf]) for tf in HTF_TIMEFRAMES + (Timeframe.MINUTE_15,)},
    )
    setup_direction = _direction_from_structure(events[Timeframe.HOUR_1])
    setup = _build_setup(
        events[Timeframe.MINUTE_15],
        events[Timeframe.MINUTE_5],
        price=price,
        atr=atr,
        htf_direction=htf_direction or setup_direction or "BULLISH",
    )

    htf_aligned = htf_direction is not None
    setup_structure_aligned = setup_direction == htf_direction and htf_direction is not None
    valid_poi = setup.poi is not None
    premium_discount_valid = _premium_discount_valid(events[Timeframe.MINUTE_15], htf_direction) if htf_direction else False
    liquidity_sweep_confirmed = setup.sweep is not None
    displacement_confirmed = setup.displacement is not None
    micro_structure_confirmed = setup.micro_break is not None
    entry_location_valid = valid_poi and premium_discount_valid
    structural_stop_valid = setup.stop_loss is not None and setup.stop_loss > 0
    opposing_liquidity_target = setup.opposing_target is not None
    minimum_rr_met = setup.risk_reward is not None and setup.risk_reward >= MINIMUM_RR

    checks = {
        "htf_bias": htf_direction or "UNKNOWN",
        "htf_aligned": htf_aligned,
        "setup_structure_aligned": setup_structure_aligned,
        "valid_poi": valid_poi,
        "premium_discount_valid": premium_discount_valid,
        "liquidity_sweep_confirmed": liquidity_sweep_confirmed,
        "displacement_confirmed": displacement_confirmed,
        "micro_structure_confirmed": micro_structure_confirmed,
        "entry_location_valid": entry_location_valid,
        "opposing_liquidity_target": opposing_liquidity_target,
        "path_to_target_clear": setup.path_clear,
        "minimum_rr_met": minimum_rr_met,
        "session_valid": session_valid,
        "volatility_valid": volatility_valid,
        "news_filter_passed": news_filter_passed,
        "structural_stop_valid": structural_stop_valid,
    }
    hard_gates = (
        "htf_aligned", "setup_structure_aligned", "valid_poi",
        "premium_discount_valid", "liquidity_sweep_confirmed",
        "displacement_confirmed", "micro_structure_confirmed",
        "entry_location_valid", "structural_stop_valid",
        "opposing_liquidity_target", "path_to_target_clear",
        "minimum_rr_met", "session_valid", "volatility_valid", "news_filter_passed",
    )
    failed = tuple(key for key in hard_gates if not checks[key])
    quality = _quality_score(checks, setup.sweep, setup.displacement, setup.micro_break)
    hard_pass = not failed and htf_direction is not None
    risk_policy = RiskPolicy()
    risk_per_trade = account_risk_per_trade if account_risk_per_trade is not None else risk_policy.risk_per_trade
    if not 0.005 <= risk_per_trade <= 0.01:
        hard_pass = False
        failed = (*failed, "risk_per_trade_policy")
    direction = setup.direction if htf_direction else SignalDirection.NEUTRAL
    if not hard_pass:
        direction = SignalDirection.NEUTRAL
    score = quality if setup.direction in {SignalDirection.STRONG_BUY, SignalDirection.BUY} else -quality
    components: list[SignalComponent] = []
    for tf in required:
        tf_direction = _direction_from_structure(events[tf])
        tf_score = 1.0 if tf_direction == "BULLISH" else -1.0 if tf_direction == "BEARISH" else 0.0
        components.append(SignalComponent(
            timeframe=tf.value,
            indicator_score=0.0,
            smc_score=tf_score,
            combined_score=tf_score,
            evidence=(f"{tf.value}: deterministic market-structure direction {tf_direction or 'UNKNOWN'}.",),
        ))

    contract = None
    if hard_pass and setup.stop_loss is not None and setup.opposing_target is not None:
        contract = build_trade_contract(
            direction="BUY" if direction in {SignalDirection.BUY, SignalDirection.STRONG_BUY} else "SELL",
            entry_price=price,
            stop_distance=abs(price - setup.stop_loss),
            target_price=setup.opposing_target,
            spread_bps=0.0,
            slippage_bps=0.0,
            fee_bps=0.0,
        )

    regime = detect_regime(m15)
    family_values: dict[str, float] = {}
    expected_value = None
    probability = None

    signal = CryptoSignal(
        symbol=datasets[Timeframe.DAY_1].symbol,
        signal=direction,
        score=score,
        signal_strength=quality,
        confidence=quality,
        calibrated_probability=probability,
        confluence=quality,
        confluence_families=tuple(sorted(k for k, v in family_values.items() if abs(v) >= 0.15)),
        expected_value_r=expected_value,
        risk_reward=setup.risk_reward,
        risk_reward_status=RiskRewardStatus.AVAILABLE if setup.risk_reward is not None else RiskRewardStatus.UNAVAILABLE,
        risk_reward_reason=None if minimum_rr_met else "Enhanced Signal requires a minimum 2.00:1 RR.",
        structural_target=setup.opposing_target,
        atr_minimum_target=None,
        price=price,
        entry_price=price,
        stop_loss=contract.stop_loss if contract else setup.stop_loss,
        take_profit=contract.take_profit if contract else setup.opposing_target,
        atr=atr,
        stop_distance=abs(price - setup.stop_loss) if setup.stop_loss else None,
        position_size=contract.position_size if contract else None,
        expected_cost=contract.expected_cost if contract else 0.0,
        expected_slippage=contract.expected_slippage if contract else 0.0,
        expected_spread=contract.expected_spread if contract else 0.0,
        calculated_at=datetime.now(timezone.utc),
        latest_candle_timestamp=m5.completed_candles[-1].timestamp,
        source=m5.source,
        components=tuple(components),
        evidence=tuple([
            f"HTF bias: {htf_direction or 'NOT ALIGNED'}.",
            f"15m POI: {setup.poi.type if setup.poi else 'NONE'}.",
            f"5m liquidity sweep: {setup.sweep.type if setup.sweep else 'NONE'}.",
            f"5m displacement: {setup.displacement.type if setup.displacement else 'NONE'}.",
            f"5m micro structure: {setup.micro_break.type if setup.micro_break else 'NONE'}.",
            *setup.reasons,
        ][:30]),
        research_eligible=hard_pass,
        qualification_reasons=failed,
        minimum_confidence=0.0,
        minimum_risk_reward=MINIMUM_RR,
        qualification_status="QUALIFIED" if hard_pass else "REJECTED",
        mtf_bias=mtf.research.bias.value,
        mtf_alignment=mtf.research.alignment_count,
        regime=regime.regime.value,
        regime_confidence=regime.confidence,
        market_structure=", ".join(e.type for e in sorted(events[Timeframe.MINUTE_15], key=lambda e: e.time)[-8:]) or "NONE",
        liquidity_conditions=setup.sweep.type if setup.sweep else "NO_CONFIRMED_SWEEP",
        momentum=None,
        volatility=session.volatility_score / 100 if session.volatility_score is not None else None,
        session=session.label,
        strategy="enhanced_smc",
        signal_engine_version=APPLICATION_VERSION,
        feature_version=METHODOLOGY_VERSION,
        scoring_policy_version="enhanced-hard-gates-v1",
        risk_policy_version=risk_policy.policy_version,
        execution_model_version="execution-v1",
        structural_conditions={
            "htf_biases": dict(zip((tf.value for tf in HTF_TIMEFRAMES), htf_biases)),
            "poi": setup.poi.type if setup.poi else None,
            "poi_price": float(setup.poi.price) if setup.poi else None,
            "sweep": setup.sweep.type if setup.sweep else None,
            "displacement": setup.displacement.type if setup.displacement else None,
            "micro_break": setup.micro_break.type if setup.micro_break else None,
            "entry_model": "5m displacement close",
            "stop_model": "POI/sweep extreme + 0.10 ATR buffer",
            "target_model": "nearest opposing liquidity with >= 2.00R",
            "path_validation": setup.path_clear,
            "risk_per_trade": risk_per_trade,
            "max_daily_loss": 0.02,
            "max_correlated_positions": 2,
            "breakeven_rule": "not automated; requires empirical validation",
            "news_filter": "existing news/calendar provider hard gate",
        },
        feature_families={k: round(v, 6) for k, v in family_values.items()},
        replay_candles=tuple(
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": float(c.volume or 0.0),
                "timeframe": c.timeframe.value,
                "source": c.source,
            }
            for c in m5.completed_candles[-120:]
        ),
    )
    check_model = EnhancedSignalChecks(
        **checks,
        hard_gate_passed=hard_pass,
        quality_score=quality,
        failed_gates=failed,
    )
    return signal, check_model


def calculate_atr(dataset: OHLCVDataset, period: int = 14) -> float:
    candles = list(dataset.completed_candles)
    if len(candles) < period + 1:
        raise ValueError(f"At least {period + 1} completed candles are required for ATR.")
    trs = []
    for i in range(1, len(candles)):
        previous = candles[i - 1].close
        trs.append(max(candles[i].high - candles[i].low, abs(candles[i].high - previous), abs(candles[i].low - previous)))
    return sum(trs[-period:]) / period
