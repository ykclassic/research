from __future__ import annotations

from typing import Any

from app.preferences.models import UserPreferencesRecord, default_preferences
from app.preferences.repository import get_preferences, upsert_preferences
from app.preferences.schemas import UserPreferences
from app.symbols import normalize_symbol


class PreferencesService:
    """Coordinates validated, user-scoped preference reads and writes."""

    @staticmethod
    def _payload(preferences: UserPreferences) -> dict[str, Any]:
        return preferences.model_dump(mode="json")

    @staticmethod
    def _validate_research_defaults(preferences: UserPreferences) -> None:
        research = preferences.research_preferences
        mapping = normalize_symbol(research.default_asset)
        expected_class = {
            "crypto": "Crypto",
            "forex": "Forex",
            "stock": "Stocks",
            "etf": "Stocks",
        }[mapping.asset_class]
        if research.default_asset_class != expected_class:
            raise ValueError(
                "Default asset class does not match the default asset. "
                f"{mapping.internal} belongs to {expected_class}."
            )

    def get_or_create(self, access_token: str, user_id: str) -> UserPreferencesRecord:
        existing = get_preferences(access_token, user_id)
        if existing is not None:
            return existing
        defaults = UserPreferences.model_validate(default_preferences())
        self._validate_research_defaults(defaults)
        return upsert_preferences(access_token, user_id, self._payload(defaults))

    def update(self, access_token: str, user_id: str, preferences: UserPreferences) -> UserPreferencesRecord:
        self._validate_research_defaults(preferences)
        return upsert_preferences(access_token, user_id, self._payload(preferences))

    def reset(self, access_token: str, user_id: str) -> UserPreferencesRecord:
        defaults = UserPreferences.model_validate(default_preferences())
        self._validate_research_defaults(defaults)
        return upsert_preferences(access_token, user_id, self._payload(defaults))


preferences_service = PreferencesService()
