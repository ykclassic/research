"""Compatibility facade for the deterministic signal engine."""
from app.services.signal_engine_v2 import (
    CONFIDENCE_BASE, CONFIDENCE_SCORE_SCALE, SIGNAL_LEVEL_LOOKBACK,
    SIGNAL_STOP_ATR_MULTIPLIER, TIMEFRAME_WEIGHTS, CandidateTradeLevels,
    _candidate_trade_levels, _confidence_from_score, _qualify, _signal_for_score,
    _structural_levels, generate_crypto_signal,
)

__all__ = [
    "CONFIDENCE_BASE", "CONFIDENCE_SCORE_SCALE", "SIGNAL_LEVEL_LOOKBACK",
    "SIGNAL_STOP_ATR_MULTIPLIER", "TIMEFRAME_WEIGHTS", "CandidateTradeLevels",
    "_candidate_trade_levels", "_confidence_from_score", "_qualify",
    "_signal_for_score", "_structural_levels", "generate_crypto_signal",
]
