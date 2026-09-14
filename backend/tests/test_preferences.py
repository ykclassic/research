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
    assert preferences.display_preferences.theme == "system"
    assert preferences.display_preferences.density == "comfortable"
    assert preferences.display_preferences.default_landing_page == "/dashboard"
    assert preferences.display_preferences.decimal_precision == "auto"
    assert preferences.display_preferences.chart_type == "candlestick"
    assert preferences.display_preferences.show_volume is True
    assert preferences.display_preferences.remember_zoom is True
    assert preferences.display_preferences.auto_refresh is True
    assert preferences.display_preferences.reduced_motion is False
    assert preferences.display_preferences.accessible_contrast is False
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


def test_display_preferences_reject_unsupported_landing_page() -> None:
    values = default_preferences()
    values["display_preferences"]["default_landing_page"] = "/admin"
    with pytest.raises(ValidationError):
        UserPreferences.model_validate(values)


def test_display_preferences_reject_unsupported_chart_type() -> None:
    values = default_preferences()
    values["display_preferences"]["chart_type"] = "renko"
    with pytest.raises(ValidationError):
        UserPreferences.model_validate(values)


def test_privacy_retention_accepts_supported_values() -> None:
    for days in (30, 90, 365, 0):
        values = default_preferences()
        values["privacy_preferences"]["research_history_retention_days"] = days
        assert UserPreferences.model_validate(values).privacy_preferences.research_history_retention_days == days


def test_privacy_retention_rejects_unsupported_values() -> None:
    values = default_preferences()
    values["privacy_preferences"]["research_history_retention_days"] = 180
    with pytest.raises(ValidationError):
        UserPreferences.model_validate(values)
