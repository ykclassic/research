from __future__ import annotations

import pytest

from app.preferences.models import default_preferences
from app.preferences.schemas import UserPreferences
from app.services.research_preferences import resolve_research_preferences


def test_default_research_configuration_is_canonical() -> None:
    preferences = UserPreferences.model_validate(default_preferences())
    configuration = resolve_research_preferences(None)

    assert configuration.default_asset == "BTC/USD"
    assert configuration.default_asset_class == "Crypto"
    assert configuration.default_timeframe == "1h"
    assert configuration.analysis_depth == "Standard"
    assert configuration.requested_components == {
        "technical_analysis": True,
        "market_structure": True,
        "multi_timeframe": True,
        "fundamental_analysis": True,
        "news_analysis": True,
        "ai_interpretation": True,
    }
    assert configuration.data_limit == 300
    assert preferences.research_preferences.model_dump() == {
        "default_asset": "BTC/USD",
        "default_asset_class": "Crypto",
        "default_timeframe": "1h",
        "analysis_depth": "Standard",
        "technical_analysis_enabled": True,
        "market_structure_enabled": True,
        "multi_timeframe_enabled": True,
        "fundamental_analysis_enabled": True,
        "news_analysis_enabled": True,
        "ai_interpretation_enabled": True,
    }


def test_analysis_depth_only_changes_requested_data_window() -> None:
    values = default_preferences()
    values["research_preferences"]["analysis_depth"] = "Quick"
    quick = resolve_research_preferences(_record_from_values(values))

    values["research_preferences"]["analysis_depth"] = "Comprehensive"
    comprehensive = resolve_research_preferences(_record_from_values(values))

    assert quick.data_limit == 220
    assert comprehensive.data_limit == 500
    assert quick.requested_components == comprehensive.requested_components


def test_research_preferences_reject_unknown_default_asset() -> None:
    values = default_preferences()
    values["research_preferences"]["default_asset"] = "UNKNOWN/USD"

    with pytest.raises(ValueError, match="Unsupported symbol"):
        resolve_research_preferences(_record_from_values(values))


def test_research_preferences_reject_mismatched_asset_class() -> None:
    values = default_preferences()
    values["research_preferences"]["default_asset"] = "ETH/USD"
    values["research_preferences"]["default_asset_class"] = "Forex"

    with pytest.raises(ValueError, match="does not match"):
        resolve_research_preferences(_record_from_values(values))


def _record_from_values(values: dict) -> object:
    """Build the smallest record-shaped object required by the resolver."""
    class Record:
        research_preferences = values["research_preferences"]

    return Record()
