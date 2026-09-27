import pytest

from app.services.signal_feature_engine import FeatureFamily, family_score
from app.services.signal_validation import calibrate, cosine_similarity, fit_platt_calibration, purged_walk_forward_timestamps
from app.services.trade_contract import build_trade_contract


def test_family_score_does_not_double_count_missing_families():
    score = family_score((FeatureFamily("trend", 1.0, 1.0), FeatureFamily("momentum", -1.0, 1.0)))
    assert -1 <= score <= 1
    assert score == pytest.approx((0.25 - 0.20) / 0.45)


def test_trade_contract_is_single_source_for_levels_and_costs():
    contract = build_trade_contract(direction="BUY", entry_price=100, stop_distance=2, target_price=106, account_equity=10000, risk_fraction=0.01, spread_bps=5, slippage_bps=5, fee_bps=4)
    assert contract.valid
    assert contract.stop_loss == 98
    assert contract.reward_risk == pytest.approx(3.0)
    assert contract.position_size == pytest.approx(50.0)
    assert contract.expected_cost == pytest.approx(0.14)


def test_calibration_is_not_claimed_without_sample():
    result = calibrate([0.5] * 10, [1, 0] * 5)
    assert result.sample_size == 10
    assert not result.calibrated_probability_available


def test_platt_calibration_requires_both_classes_and_minimum_sample():
    scores = [i / 20 for i in range(20)]
    outcomes = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
    a, b = fit_platt_calibration(scores, outcomes)
    assert a == pytest.approx(a)
    assert 0 < 1 / (1 + __import__('math').exp(-(a * 0.75 + b))) < 1


def test_purged_walk_forward_has_embargo_between_validation_and_test():
    windows = purged_walk_forward_timestamps(tuple(range(60)), 20, 10, 10, embargo=2)
    assert windows
    train, validation, test = windows[0]
    assert max(validation) < min(test)
    assert min(test) == 32


def test_cosine_similarity_is_bounded():
    assert cosine_similarity((1, 0), (1, 0)) == pytest.approx(1.0)
    assert cosine_similarity((1, 0), (-1, 0)) == pytest.approx(-1.0)
