from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.settings_integration import (
    frequency_allows,
    market_data_policy,
    validate_dataset_policy,
    validate_quote_policy,
)


def test_market_data_policy_uses_saved_preferences():
    record = SimpleNamespace(
        market_data_preferences={
            "maximum_data_age_seconds": 60,
            "reject_stale_data": True,
            "require_completed_candles": True,
            "allow_cached_data_fallback": False,
        }
    )
    policy = market_data_policy(record)
    assert policy.maximum_data_age_seconds == 60
    assert policy.reject_stale_data is True
    assert policy.require_completed_candles is True
    assert policy.allow_cached_data_fallback is False


def test_frequency_off_blocks_alert_delivery():
    assert not frequency_allows(None, {"frequency": "Off"}, datetime.now(timezone.utc))


def test_frequency_batched_throttles_recent_alert():
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(minutes=5)).isoformat()
    old = (now - timedelta(minutes=16)).isoformat()
    preferences = {"frequency": "Batched"}
    assert not frequency_allows(recent, preferences, now)
    assert frequency_allows(old, preferences, now)


def test_stale_dataset_is_rejected():
    dataset = SimpleNamespace(
        symbol="BTC/USD",
        timeframe=SimpleNamespace(value="1h"),
        completed_candles=[object()],
        freshness_age_seconds=61,
        freshness_status=SimpleNamespace(value="FRESH"),
        cache_hit=False,
        fallback_used=False,
    )
    policy = SimpleNamespace(
        maximum_data_age_seconds=60,
        reject_stale_data=True,
        require_completed_candles=True,
        allow_cached_data_fallback=True,
    )
    with pytest.raises(ValueError, match="stale"):
        validate_dataset_policy(dataset, policy)


def test_cache_fallback_can_be_rejected_for_quotes():
    quote = SimpleNamespace(
        symbol="BTC/USD",
        status="LIVE",
        freshness_age_seconds=1,
        cache_hit=True,
        fallback_used=True,
    )
    policy = SimpleNamespace(
        maximum_data_age_seconds=30,
        reject_stale_data=True,
        require_completed_candles=True,
        allow_cached_data_fallback=False,
    )
    with pytest.raises(ValueError, match="cache fallback"):
        validate_quote_policy(quote, policy)
