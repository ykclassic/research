import pytest
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


def test_confidence_mapping_is_fixed_monotonic_and_threshold_boundary() -> None:
    from app.services.signal_engine import _confidence_from_score

    assert _confidence_from_score(0.0) == 0.50
    assert _confidence_from_score(0.40) == 0.70
    assert _confidence_from_score(0.60) == 0.80
    assert _confidence_from_score(0.64) == pytest.approx(0.82)
    assert _confidence_from_score(-0.64) == pytest.approx(0.82)
    assert _confidence_from_score(0.80) == 0.90
    assert _confidence_from_score(1.0) == 1.0
    assert _confidence_from_score(0.65) > _confidence_from_score(0.64)


def test_confidence_mapping_does_not_adapt_to_preference_threshold() -> None:
    from app.services.signal_engine import _confidence_from_score

    # Qualification policy may change independently; the deterministic score
    # mapping itself must remain unchanged.
    assert _confidence_from_score(0.64) == pytest.approx(0.82)
    assert _confidence_from_score(0.64) == _confidence_from_score(-0.64)
