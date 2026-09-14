from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.preferences.models import UserPreferencesRecord, default_preferences
from app.preferences.repository import get_preferences
from app.preferences.schemas import MarketDataPreferences, ResearchPreferences
from app.symbols import normalize_symbol


@dataclass(frozen=True)
class MarketDataPolicy:
    maximum_data_age_seconds: int
    reject_stale_data: bool
    require_completed_candles: bool
    allow_cached_data_fallback: bool


def merged_preferences(access_token: str, user_id: str) -> UserPreferencesRecord | None:
    """Load the authenticated user's settings without creating duplicate policy logic."""
    return get_preferences(access_token, user_id)


def default_research_preferences() -> ResearchPreferences:
    return ResearchPreferences.model_validate(default_preferences()["research_preferences"])


def research_preferences(record: UserPreferencesRecord | None) -> ResearchPreferences:
    payload = record.research_preferences if record is not None else default_preferences()["research_preferences"]
    return ResearchPreferences.model_validate(payload)


def market_data_policy(record: UserPreferencesRecord | None) -> MarketDataPolicy:
    payload = record.market_data_preferences if record is not None else default_preferences()["market_data_preferences"]
    value = MarketDataPreferences.model_validate(payload)
    return MarketDataPolicy(
        maximum_data_age_seconds=value.maximum_data_age_seconds,
        reject_stale_data=value.reject_stale_data,
        require_completed_candles=value.require_completed_candles,
        allow_cached_data_fallback=value.allow_cached_data_fallback,
    )


def default_timeframe(record: UserPreferencesRecord | None, fallback: str = "1h") -> str:
    try:
        return research_preferences(record).default_timeframe
    except ValueError:
        return fallback


def default_asset(record: UserPreferencesRecord | None, fallback: str = "BTC/USD") -> str:
    try:
        return normalize_symbol(research_preferences(record).default_asset).internal
    except ValueError:
        return fallback


def analysis_limit(record: UserPreferencesRecord | None, fallback: int = 250) -> int:
    depth = research_preferences(record).analysis_depth
    return {"Quick": 220, "Standard": 300, "Comprehensive": 500}.get(depth, fallback)


def _completed_candles(dataset: Any) -> list[Any]:
    """Return completed candles while remaining compatible with legacy test doubles."""
    completed = getattr(dataset, "completed_candles", None)
    if completed is not None:
        return list(completed)
    candles = getattr(dataset, "candles", None)
    if candles is None:
        return []
    return [candle for candle in candles if getattr(candle, "is_complete", True)]


def validate_dataset_policy(dataset: Any, policy: MarketDataPolicy) -> None:
    completed = _completed_candles(dataset)
    if policy.require_completed_candles and not completed:
        raise ValueError(
            f"No completed candles are available for {dataset.symbol} {dataset.timeframe.value}."
        )
    age = getattr(dataset, "freshness_age_seconds", None)
    freshness = getattr(getattr(dataset, "freshness_status", None), "value", None)
    timeframe_seconds = getattr(getattr(dataset, "timeframe", None), "seconds", 0) or 0
    # Candle freshness is measured from the close of the latest completed
    # candle. A 1h candle can therefore legitimately be 30+ seconds old while
    # still representing the current completed market state. Apply the user's
    # tolerance after the timeframe duration rather than comparing candle age
    # directly with the point-in-time quote threshold.
    stale = age is not None and (
        freshness == "STALE" or age > timeframe_seconds + policy.maximum_data_age_seconds
    )
    if policy.reject_stale_data and stale:
        raise ValueError(
            f"Market candles for {dataset.symbol} {dataset.timeframe.value} are stale "
            f"({age:.1f}s since candle close); allowed timeframe age is "
            f"{timeframe_seconds + policy.maximum_data_age_seconds}s."
        )
    if not policy.allow_cached_data_fallback and getattr(dataset, "cache_hit", False) and getattr(dataset, "fallback_used", False):
        raise ValueError(
            f"Validated cache fallback is disabled for {dataset.symbol} {dataset.timeframe.value}; live market data is required."
        )


def validate_quote_policy(quote: Any, policy: MarketDataPolicy) -> None:
    age = getattr(quote, "freshness_age_seconds", None)
    status = getattr(getattr(quote, "status", None), "value", getattr(quote, "status", None))
    stale = age is not None and (status == "STALE" or age > policy.maximum_data_age_seconds)
    if policy.reject_stale_data and stale:
        raise ValueError(
            f"Market quote for {quote.symbol} is stale ({age:.1f}s); maximum acceptable age is {policy.maximum_data_age_seconds}s."
        )
    if not policy.allow_cached_data_fallback and getattr(quote, "cache_hit", False) and getattr(quote, "fallback_used", False):
        raise ValueError(
            f"Validated cache fallback is disabled for {quote.symbol}; live market data is required."
        )


def frequency_window_seconds(preferences: dict[str, Any]) -> int | None:
    frequency = preferences.get("frequency", "Immediate")
    if frequency == "Batched":
        return 15 * 60
    if frequency == "Daily digest":
        return 24 * 60 * 60
    if frequency == "Off":
        return 0
    return None


def frequency_allows(last_triggered_at: str | None, preferences: dict[str, Any], now: datetime) -> bool:
    window = frequency_window_seconds(preferences)
    if window == 0:
        return False
    if window is None or not last_triggered_at:
        return True
    try:
        previous = datetime.fromisoformat(last_triggered_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if previous.tzinfo is None or previous.utcoffset() is None:
        previous = previous.replace(tzinfo=timezone.utc)
    return now - previous >= timedelta(seconds=window)
