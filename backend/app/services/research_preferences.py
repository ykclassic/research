from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.preferences.models import UserPreferencesRecord, default_preferences
from app.preferences.schemas import MarketDataPreferences, ResearchPreferences
from app.symbols import normalize_symbol


@dataclass(frozen=True)
class ResearchRequestConfiguration:
    """Resolved user-level research configuration.

    This object controls orchestration only. It never changes the formulas,
    thresholds, or implementation of the underlying analytical services.
    """

    default_asset: str
    default_asset_class: str
    default_timeframe: str
    analysis_depth: str
    technical_analysis_enabled: bool
    market_structure_enabled: bool
    multi_timeframe_enabled: bool
    fundamental_analysis_enabled: bool
    news_analysis_enabled: bool
    ai_interpretation_enabled: bool
    maximum_data_age_seconds: int = 30
    reject_stale_data: bool = True
    require_completed_candles: bool = True
    allow_cached_data_fallback: bool = True

    @property
    def requested_components(self) -> dict[str, bool]:
        return {
            "technical_analysis": self.technical_analysis_enabled,
            "market_structure": self.market_structure_enabled,
            "multi_timeframe": self.multi_timeframe_enabled,
            "fundamental_analysis": self.fundamental_analysis_enabled,
            "news_analysis": self.news_analysis_enabled,
            "ai_interpretation": self.ai_interpretation_enabled,
        }

    @property
    def data_limit(self) -> int:
        """Select the requested evidence window without changing algorithms."""
        return {
            "Quick": 220,
            "Standard": 300,
            "Comprehensive": 500,
        }[self.analysis_depth]

    def primary_timeframe(self) -> str:
        return self.default_timeframe


def _asset_class_for_symbol(symbol: str) -> str:
    asset_class = normalize_symbol(symbol).asset_class
    if asset_class == "crypto":
        return "Crypto"
    if asset_class == "forex":
        return "Forex"
    return "Stocks"


def resolve_research_preferences(
    record: UserPreferencesRecord | None,
) -> ResearchRequestConfiguration:
    """Resolve persisted preferences, falling back to canonical defaults."""
    defaults = default_preferences()
    if record is None:
        research_payload: dict[str, Any] = defaults["research_preferences"]
        market_data_payload: dict[str, Any] = defaults["market_data_preferences"]
    else:
        research_payload = record.research_preferences
        market_data_payload = getattr(record, "market_data_preferences", defaults["market_data_preferences"])

    preferences = ResearchPreferences.model_validate(research_payload)
    market_data = MarketDataPreferences.model_validate(market_data_payload)
    normalized_asset = normalize_symbol(preferences.default_asset).internal
    expected_class = _asset_class_for_symbol(normalized_asset)
    if expected_class != preferences.default_asset_class:
        raise ValueError(
            "Default asset class does not match the default asset. "
            f"{normalized_asset} belongs to {expected_class}."
        )

    return ResearchRequestConfiguration(
        default_asset=normalized_asset,
        default_asset_class=preferences.default_asset_class,
        default_timeframe=preferences.default_timeframe,
        analysis_depth=preferences.analysis_depth,
        technical_analysis_enabled=preferences.technical_analysis_enabled,
        market_structure_enabled=preferences.market_structure_enabled,
        multi_timeframe_enabled=preferences.multi_timeframe_enabled,
        fundamental_analysis_enabled=preferences.fundamental_analysis_enabled,
        news_analysis_enabled=preferences.news_analysis_enabled,
        ai_interpretation_enabled=preferences.ai_interpretation_enabled,
        maximum_data_age_seconds=market_data.maximum_data_age_seconds,
        reject_stale_data=market_data.reject_stale_data,
        require_completed_candles=market_data.require_completed_candles,
        allow_cached_data_fallback=market_data.allow_cached_data_fallback,
    )


def configuration_from_record(record: UserPreferencesRecord) -> ResearchRequestConfiguration:
    """Named adapter for callers that already loaded user preferences."""
    return resolve_research_preferences(record)
