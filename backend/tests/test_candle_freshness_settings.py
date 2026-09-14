from types import SimpleNamespace

import pytest

from app.services.settings_integration import MarketDataPolicy, validate_dataset_policy


def dataset(*, timeframe_seconds: int, age: float, freshness: str = "FRESH") -> SimpleNamespace:
    return SimpleNamespace(
        symbol="BTC/USD",
        timeframe=SimpleNamespace(value="1h", seconds=timeframe_seconds),
        completed_candles=[object()],
        freshness_age_seconds=age,
        freshness_status=SimpleNamespace(value=freshness),
        cache_hit=False,
        fallback_used=False,
    )


def policy(maximum_age: int = 30) -> MarketDataPolicy:
    return MarketDataPolicy(
        maximum_data_age_seconds=maximum_age,
        reject_stale_data=True,
        require_completed_candles=True,
        allow_cached_data_fallback=True,
    )


def test_one_hour_candle_can_be_older_than_quote_tolerance_without_being_stale():
    validate_dataset_policy(dataset(timeframe_seconds=3600, age=39.81), policy(30))


def test_one_hour_candle_is_rejected_after_timeframe_plus_tolerance():
    with pytest.raises(ValueError, match="stale"):
        validate_dataset_policy(dataset(timeframe_seconds=3600, age=3631), policy(30))


def test_provider_declared_stale_remains_rejected():
    with pytest.raises(ValueError, match="stale"):
        validate_dataset_policy(dataset(timeframe_seconds=3600, age=10, freshness="STALE"), policy(30))
