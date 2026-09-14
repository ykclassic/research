from __future__ import annotations

from app.models.mtf import MTFBias
from app.models.signal import SignalDirection
from app.services.signal_engine import _qualify


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
