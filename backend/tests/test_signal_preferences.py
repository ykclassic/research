from __future__ import annotations

from types import SimpleNamespace

from app.models.mtf import MTFBias
from app.models.signal import SignalDirection
from app.services.signal_engine import (
    SIGNAL_STOP_ATR_MULTIPLIER,
    _candidate_trade_levels,
    _qualify,
)


def _preferences(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "minimum_confidence": 0.82,
        "preferred_signal_types": ["BUY", "SELL", "NEUTRAL"],
        "minimum_risk_reward": 1.5,
        "require_multi_timeframe_confirmation": False,
        "require_market_structure_confirmation": False,
    }
    values.update(overrides)
    return values


def _candle(high: float, low: float) -> SimpleNamespace:
    return SimpleNamespace(high=high, low=low)


def test_confidence_threshold_is_enforced_server_side() -> None:
    qualified, reasons = _qualify(
        SignalDirection.BUY, 0.81, 2.0, MTFBias.BULLISH, 4, 0.8, _preferences()
    )
    assert not qualified
    assert "below" in reasons[0]


def test_preferred_signal_type_is_enforced() -> None:
    qualified, reasons = _qualify(
        SignalDirection.BUY, 0.95, 2.0, MTFBias.BULLISH, 4, 0.8,
        _preferences(preferred_signal_types=["SELL"]),
    )
    assert not qualified
    assert any("not an enabled preferred signal type" in reason for reason in reasons)


def test_risk_reward_is_enforced_for_directional_signals() -> None:
    qualified, reasons = _qualify(
        SignalDirection.SELL, 0.95, 1.2, MTFBias.BEARISH, 4, -0.8, _preferences()
    )
    assert not qualified
    assert any("Risk/reward" in reason for reason in reasons)


def test_neutral_signal_does_not_require_directional_risk_reward() -> None:
    qualified, reasons = _qualify(
        SignalDirection.NEUTRAL, 0.90, 0.0, MTFBias.NEUTRAL, 0, 0.0, _preferences()
    )
    assert qualified
    assert reasons == ()


def test_mtf_confirmation_requires_alignment() -> None:
    qualified, reasons = _qualify(
        SignalDirection.BUY, 0.95, 2.0, MTFBias.BULLISH, 2, 0.8,
        _preferences(require_multi_timeframe_confirmation=True),
    )
    assert not qualified
    assert any("Multi-timeframe" in reason for reason in reasons)


def test_structure_confirmation_requires_directional_score() -> None:
    qualified, reasons = _qualify(
        SignalDirection.SELL, 0.95, 2.0, MTFBias.BEARISH, 4, 0.2,
        _preferences(require_market_structure_confirmation=True),
    )
    assert not qualified
    assert any("Market-structure" in reason for reason in reasons)


def test_candidate_levels_reject_very_tight_structural_resistance() -> None:
    levels = _candidate_trade_levels(
        SignalDirection.BUY, 100.0, 2.0, [_candle(100.5, 98.0)], 1.5
    )
    assert levels.stop_loss == 97.0
    assert levels.structural_target == 100.5
    assert levels.take_profit is None
    assert levels.risk_reward == 0.5 / 3.0
    assert any("does not satisfy" in r for r in levels.reasons)
    assert any("Nearest structural target" in r for r in levels.reasons)


def test_candidate_levels_reject_when_all_structural_targets_fail_rr() -> None:
    levels = _candidate_trade_levels(
        SignalDirection.BUY,
        100.0,
        2.0,
        [_candle(103.0, 98.0), _candle(103.5, 99.0)],
        1.5,
        stop_atr_multiplier=2.0,
    )
    assert levels.take_profit is None
    assert levels.risk_reward == 3.0 / 4.0
    assert any("does not satisfy" in r for r in levels.reasons)
    assert any("Nearest structural target" in r for r in levels.reasons)


def test_candidate_levels_accept_valid_structural_rr() -> None:
    levels = _candidate_trade_levels(
        SignalDirection.BUY, 100.0, 2.0, [_candle(105.0, 98.0)], 1.5
    )
    assert levels.stop_distance == 3.0
    assert levels.stop_loss == 97.0
    assert levels.atr_minimum_target == 104.5
    assert levels.take_profit == 105.0
    assert levels.risk_reward == 5.0 / 3.0
    assert levels.reasons == ()


def test_candidate_levels_scan_to_next_resistance_when_nearest_fails_rr() -> None:
    levels = _candidate_trade_levels(
        SignalDirection.BUY,
        100.0,
        2.0,
        [_candle(100.5, 98.0), _candle(105.0, 99.0)],
        1.5,
    )
    assert levels.structural_target == 105.0
    assert levels.take_profit == 105.0
    assert levels.risk_reward == 5.0 / 3.0
    assert levels.reasons == ()


def test_candidate_levels_are_symmetric_for_buy_and_sell() -> None:
    buy = _candidate_trade_levels(
        SignalDirection.BUY, 100.0, 2.0, [_candle(105.0, 95.0)], 1.5
    )
    sell = _candidate_trade_levels(
        SignalDirection.SELL, 100.0, 2.0, [_candle(105.0, 95.0)], 1.5
    )
    assert buy.stop_loss == 97.0
    assert sell.stop_loss == 103.0
    assert buy.take_profit == 105.0
    assert sell.take_profit == 95.0
    assert buy.risk_reward == sell.risk_reward == 5.0 / 3.0


def test_candidate_levels_scan_to_next_support_when_nearest_fails_rr() -> None:
    levels = _candidate_trade_levels(
        SignalDirection.SELL,
        100.0,
        2.0,
        [_candle(102.0, 99.5), _candle(101.0, 95.0)],
        1.5,
    )
    assert levels.structural_target == 95.0
    assert levels.take_profit == 95.0
    assert levels.risk_reward == 5.0 / 3.0
    assert levels.reasons == ()


def test_candidate_levels_reject_missing_structural_levels() -> None:
    levels = _candidate_trade_levels(
        SignalDirection.BUY, 100.0, 2.0, [_candle(100.0, 100.0)], 1.5
    )
    assert levels.structural_target is None
    assert levels.take_profit is None
    assert levels.risk_reward == 0.0
    assert any("No structural resistance" in r for r in levels.reasons)


def test_candidate_levels_reject_conflicting_structural_and_atr_targets() -> None:
    levels = _candidate_trade_levels(
        SignalDirection.SELL, 100.0, 2.0, [_candle(105.0, 99.0)], 1.5
    )
    assert levels.structural_target == 99.0
    assert levels.atr_minimum_target == 95.5
    assert levels.take_profit == 99.0
    assert levels.risk_reward == 1.0 / 3.0
    assert any("conflicts with the ATR-derived minimum target" in r for r in levels.reasons)
    assert any("below the 1.50 minimum" in r for r in levels.reasons)


def test_signal_stop_multiplier_remains_aligned_with_risk_policy() -> None:
    assert SIGNAL_STOP_ATR_MULTIPLIER == 1.5
