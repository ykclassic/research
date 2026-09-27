"""Compatibility facade for the deterministic signal engine.

The v2 implementation is intentionally isolated so downstream API/scanner imports
remain stable while the signal contract evolves.
"""
from app.services.signal_engine_v2 import (
    CONFIDENCE_BASE,
    CONFIDENCE_SCORE_SCALE,
    SIGNAL_LEVEL_LOOKBACK,
    SIGNAL_STOP_ATR_MULTIPLIER,
    TIMEFRAME_WEIGHTS,
    CandidateTradeLevels,
    _candidate_trade_levels,
    _confidence_from_score,
    _qualify,
    _signal_for_score,
    generate_crypto_signal,
)

__all__ = [
    "CONFIDENCE_BASE", "CONFIDENCE_SCORE_SCALE", "SIGNAL_LEVEL_LOOKBACK",
    "SIGNAL_STOP_ATR_MULTIPLIER", "TIMEFRAME_WEIGHTS", "CandidateTradeLevels",
    "_candidate_trade_levels", "_confidence_from_score", "_qualify",
    "_signal_for_score", "generate_crypto_signal",
]
