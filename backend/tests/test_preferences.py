from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.preferences.models import default_preferences
from app.preferences.schemas import UserPreferences


def test_default_preferences_validate_and_are_complete() -> None:
    preferences = UserPreferences.model_validate(default_preferences())

    assert preferences.research_preferences.default_asset == "BTC/USD"
    assert preferences.research_preferences.default_timeframe == "1h"
    assert preferences.signal_preferences.minimum_confidence == 0.82
    assert preferences.market_data_preferences.require_completed_candles is True
    assert preferences.display_preferences.timezone == "Africa/Lagos"
    assert preferences.ai_preferences.output_sections.executive_summary is True
    assert preferences.privacy_preferences.research_history_retention_days == 365


def test_signal_confidence_is_bounded() -> None:
    values = default_preferences()
    values["signal_preferences"]["minimum_confidence"] = 1.2

    with pytest.raises(ValidationError):
        UserPreferences.model_validate(values)


def test_preferred_signal_types_must_be_unique() -> None:
    values = default_preferences()
    values["signal_preferences"]["preferred_signal_types"] = ["BUY", "BUY"]

    with pytest.raises(ValidationError):
        UserPreferences.model_validate(values)
