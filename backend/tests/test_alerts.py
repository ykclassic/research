import pytest

from app.services.alerts import (
    _crossed,
    _normalize_channels,
    _operator_matches,
    _validate_rule,
)


def test_rsi_operators_are_deterministic():
    assert _operator_matches(29.9, "LT", 30)
    assert _operator_matches(30, "LTE", 30)
    assert _operator_matches(70, "GTE", 70)
    assert not _operator_matches(70.1, "LT", 70)


def test_price_cross_requires_a_prior_observation():
    assert not _crossed(None, 110001, 110000, "ABOVE")
    assert _crossed(109999, 110001, 110000, "ABOVE")
    assert _crossed(110001, 109999, 110000, "BELOW")
    assert not _crossed(110001, 110002, 110000, "BELOW")


def test_rule_validation_covers_supported_conditions():
    _validate_rule({"symbol": "BTC/USD", "condition_type": "RSI_THRESHOLD", "operator": "LT", "threshold": 30, "timeframe": "1h"})
    _validate_rule({"symbol": "BTC/USD", "condition_type": "PRICE_CROSS", "operator": "ABOVE", "threshold": 110000, "timeframe": "1h"})
    _validate_rule({"symbol": "BTC/USD", "condition_type": "REGIME_CHANGE", "timeframe": "1h"})
    _validate_rule({"symbol": "BTC/USD", "condition_type": "BULLISH_BOS", "timeframe": "1h"})


def test_invalid_rsi_is_rejected():
    with pytest.raises(ValueError, match="RSI threshold"):
        _validate_rule({"symbol": "BTC/USD", "condition_type": "RSI_THRESHOLD", "operator": "LT", "threshold": 101, "timeframe": "1h"})


def test_web_channel_is_always_available_and_unknown_channels_are_rejected():
    assert _normalize_channels(["web"]) == ["WEB"]
    assert _normalize_channels(["EMAIL"]) == ["WEB", "EMAIL"]
    with pytest.raises(ValueError, match="Supported alert channels"):
        _normalize_channels(["SMS"])
