"""Compatibility facade for the deterministic signal engine."""
from dataclasses import replace
from app.services import signal_engine_v2 as _v2

CONFIDENCE_BASE = _v2.CONFIDENCE_BASE
CONFIDENCE_SCORE_SCALE = _v2.CONFIDENCE_SCORE_SCALE
SIGNAL_LEVEL_LOOKBACK = _v2.SIGNAL_LEVEL_LOOKBACK
SIGNAL_STOP_ATR_MULTIPLIER = _v2.SIGNAL_STOP_ATR_MULTIPLIER
TIMEFRAME_WEIGHTS = _v2.TIMEFRAME_WEIGHTS
CandidateTradeLevels = _v2.CandidateTradeLevels


def _signal_for_score(score):
    return _v2._signal_for_score(score)


def _confidence_from_score(score):
    return _v2._confidence_from_score(score)


def _structural_levels(candles, price):
    return _v2._structural_levels(candles, price)


def _candidate_trade_levels(*args, **kwargs):
    result = _v2._candidate_trade_levels(*args, **kwargs)
    reasons = list(result.reasons)
    signal = args[0] if args else kwargs.get("signal")
    buy = getattr(signal, "value", str(signal)).upper() in {"BUY", "STRONG_BUY"}
    if result.risk_reward is not None and result.take_profit is None:
        minimum = kwargs.get("minimum_risk_reward", args[4] if len(args) > 4 else 0.0)
        if not any("minimum risk/reward" in reason for reason in reasons):
            reasons.append(f"No structural target satisfies the {float(minimum):.2f}:1 minimum risk/reward.")
        if result.structural_target is not None and result.atr_minimum_target is not None:
            conflict = result.structural_target < result.atr_minimum_target if buy else result.structural_target > result.atr_minimum_target
            if conflict and not any("conflicts with the ATR-derived minimum target" in reason for reason in reasons):
                reasons.append(f"Structural target {result.structural_target:.8f} conflicts with the ATR-derived minimum target {result.atr_minimum_target:.8f}.")
        result = replace(result, risk_reward_reason=None, reasons=tuple(reasons))
    elif result.risk_reward is None and result.risk_reward_reason:
        direction = "resistance" if buy else "support"
        reason = f"risk/reward is unavailable because no validated structural {direction} exists beyond entry."
        result = replace(result, risk_reward_reason=reason, reasons=tuple(reasons + [f"No validated structural {direction} beyond entry."]))
    return result


def _qualify(signal, confidence=None, risk_reward=None, mtf_bias=None, mtf_alignment=0, structure_score=0.0, preferences=None, **kwargs):
    qualified, reasons = _v2._qualify(
        signal,
        confidence if confidence is not None else kwargs.get("strength", 0.0),
        risk_reward,
        mtf_bias,
        mtf_alignment,
        structure_score,
        preferences or {},
    )
    normalized = []
    for reason in reasons:
        if reason.startswith("Risk/reward does not meet ") and reason.endswith(" minimum RR."):
            threshold = reason.removeprefix("Risk/reward does not meet ").removesuffix(" minimum RR.").removesuffix(":1")
            normalized.append(f"Risk/reward is below the {threshold} minimum")
        else:
            normalized.append(reason)
    return qualified, tuple(normalized)


generate_crypto_signal = _v2.generate_crypto_signal

__all__ = [
    "CONFIDENCE_BASE", "CONFIDENCE_SCORE_SCALE", "SIGNAL_LEVEL_LOOKBACK",
    "SIGNAL_STOP_ATR_MULTIPLIER", "TIMEFRAME_WEIGHTS", "CandidateTradeLevels",
    "_candidate_trade_levels", "_confidence_from_score", "_qualify",
    "_signal_for_score", "_structural_levels", "generate_crypto_signal",
]
