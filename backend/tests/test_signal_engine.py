from app.models.signal import SignalDirection
from app.services.signal_engine import _signal_for_score


def test_signal_bands_are_exact_and_ordered():
    assert _signal_for_score(0.80) is SignalDirection.STRONG_BUY
    assert _signal_for_score(0.65) is SignalDirection.STRONG_BUY
    assert _signal_for_score(0.40) is SignalDirection.BUY
    assert _signal_for_score(0.25) is SignalDirection.BUY
    assert _signal_for_score(0.0) is SignalDirection.NEUTRAL
    assert _signal_for_score(-0.24) is SignalDirection.NEUTRAL
    assert _signal_for_score(-0.25) is SignalDirection.SELL
    assert _signal_for_score(-0.65) is SignalDirection.STRONG_SELL
    assert _signal_for_score(-0.90) is SignalDirection.STRONG_SELL


def test_signal_direction_has_only_five_states():
    assert {item.value for item in SignalDirection} == {
        "NEUTRAL",
        "BUY",
        "STRONG_BUY",
        "SELL",
        "STRONG_SELL",
    }
