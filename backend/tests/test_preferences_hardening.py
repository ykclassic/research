from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.preferences.models import default_preferences
from app.preferences.schemas import UserPreferences
from app.preferences.service import PreferencesService


def _record(**overrides):
    values = default_preferences()
    values.update(overrides)
    return SimpleNamespace(
        id="pref-1", user_id="user-a",
        research_preferences=deepcopy(values["research_preferences"]),
        signal_preferences=deepcopy(values["signal_preferences"]),
        alert_preferences=deepcopy(values["alert_preferences"]),
        market_data_preferences=deepcopy(values["market_data_preferences"]),
        display_preferences=deepcopy(values["display_preferences"]),
        ai_preferences=deepcopy(values["ai_preferences"]),
        privacy_preferences=deepcopy(values["privacy_preferences"]),
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    )


def test_defaults_are_valid_and_complete():
    preferences = UserPreferences.model_validate(default_preferences())
    assert preferences.research_preferences.default_asset == "BTC/USD"
    assert preferences.research_preferences.default_asset_class == "Crypto"
    assert preferences.market_data_preferences.maximum_data_age_seconds == 30
    assert preferences.privacy_preferences.research_history_retention_days == 365


def test_default_asset_is_normalized():
    values = default_preferences()
    values["research_preferences"]["default_asset"] = "  btc/usd  "
    assert UserPreferences.model_validate(values).research_preferences.default_asset == "BTC/USD"


def test_default_asset_class_must_match_asset():
    values = default_preferences()
    values["research_preferences"]["default_asset"] = "EUR/USD"
    values["research_preferences"]["default_asset_class"] = "Crypto"
    with pytest.raises(ValueError, match="Default asset class"):
        PreferencesService().update("token", "user-a", UserPreferences.model_validate(values))


def test_invalid_values_are_rejected():
    values = default_preferences()
    values["signal_preferences"]["minimum_confidence"] = 2
    with pytest.raises(ValidationError):
        UserPreferences.model_validate(values)

    values = default_preferences()
    values["display_preferences"]["theme"] = "<script>alert(1)</script>"
    with pytest.raises(ValidationError):
        UserPreferences.model_validate(values)


def test_timezone_must_be_valid_iana_identifier():
    values = default_preferences()
    values["display_preferences"]["timezone"] = "Africa/Lagos"
    assert UserPreferences.model_validate(values).display_preferences.timezone == "Africa/Lagos"
    values["display_preferences"]["timezone"] = "../../etc/passwd"
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        UserPreferences.model_validate(values)


def test_missing_new_preference_fields_are_filled_from_defaults():
    existing = _record()
    del existing.display_preferences["reduced_motion"]
    del existing.ai_preferences["show_conflicting_evidence"]
    merged = PreferencesService._merge_defaults(existing)
    defaults = default_preferences()
    assert merged.display_preferences.reduced_motion == defaults["display_preferences"]["reduced_motion"]
    assert merged.ai_preferences.show_conflicting_evidence == defaults["ai_preferences"]["show_conflicting_evidence"]


def test_existing_preferences_are_returned_without_rewrite_when_complete():
    existing = _record()
    with patch("app.preferences.service.get_preferences", return_value=existing) as get_preferences, patch("app.preferences.service.upsert_preferences") as upsert:
        result = PreferencesService().get_or_create("token-a", "user-a")
    assert result is existing
    get_preferences.assert_called_once_with("token-a", "user-a")
    upsert.assert_not_called()


def test_new_preferences_are_created_from_defaults():
    created = _record()
    with patch("app.preferences.service.get_preferences", return_value=None), patch("app.preferences.service.upsert_preferences", return_value=created) as upsert:
        result = PreferencesService().get_or_create("token-a", "user-a")
    assert result is created
    upsert.assert_called_once()
    assert upsert.call_args.args[:2] == ("token-a", "user-a")


def test_update_persists_validated_full_document():
    values = UserPreferences.model_validate(default_preferences())
    values.research_preferences.default_timeframe = "4h"
    saved = _record()
    with patch("app.preferences.service.upsert_preferences", return_value=saved) as upsert:
        result = PreferencesService().update("token-a", "user-a", values)
    assert result is saved
    assert upsert.call_args.args[2]["research_preferences"]["default_timeframe"] == "4h"


def test_reset_restores_defaults():
    saved = _record()
    with patch("app.preferences.service.upsert_preferences", return_value=saved) as upsert:
        result = PreferencesService().reset("token-a", "user-a")
    assert result is saved
    assert upsert.call_args.args[2] == default_preferences()


def test_user_id_is_not_taken_from_mutable_payload():
    values = UserPreferences.model_validate(default_preferences())
    saved = _record()
    with patch("app.preferences.service.upsert_preferences", return_value=saved) as upsert:
        PreferencesService().update("token-a", "user-a", values)
    assert upsert.call_args.args[1] == "user-a"


def test_concurrent_update_document_has_deterministic_full_payload_contract():
    service = PreferencesService()
    first = UserPreferences.model_validate(default_preferences())
    second = UserPreferences.model_validate(default_preferences())
    first.research_preferences.default_timeframe = "4h"
    second.display_preferences.theme = "dark"
    calls = []

    def save(token, user_id, payload):
        calls.append((token, user_id, payload))
        return _record()

    with patch("app.preferences.service.upsert_preferences", side_effect=save):
        service.update("token-a", "user-a", first)
        service.update("token-a", "user-a", second)
    assert len(calls) == 2
    assert all(call[1] == "user-a" for call in calls)
    assert calls[0][2]["research_preferences"]["default_timeframe"] == "4h"
    assert calls[1][2]["display_preferences"]["theme"] == "dark"
