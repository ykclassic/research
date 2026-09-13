from __future__ import annotations

from typing import Any

from app.preferences.models import UserPreferencesRecord, default_preferences
from app.preferences.repository import get_preferences, upsert_preferences
from app.preferences.schemas import UserPreferences


class PreferencesService:
    """Coordinates validated, user-scoped preference reads and writes."""

    @staticmethod
    def _payload(preferences: UserPreferences) -> dict[str, Any]:
        return preferences.model_dump(mode="json")

    def get_or_create(self, access_token: str, user_id: str) -> UserPreferencesRecord:
        existing = get_preferences(access_token, user_id)
        if existing is not None:
            return existing
        defaults = UserPreferences.model_validate(default_preferences())
        return upsert_preferences(access_token, user_id, self._payload(defaults))

    def update(self, access_token: str, user_id: str, preferences: UserPreferences) -> UserPreferencesRecord:
        return upsert_preferences(access_token, user_id, self._payload(preferences))

    def reset(self, access_token: str, user_id: str) -> UserPreferencesRecord:
        defaults = UserPreferences.model_validate(default_preferences())
        return upsert_preferences(access_token, user_id, self._payload(defaults))


preferences_service = PreferencesService()
