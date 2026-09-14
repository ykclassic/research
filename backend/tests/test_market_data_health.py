from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.models import Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus
from app.services.market_data_health import MarketDataHealthService


class FakeProvider:
    name = "fake_provider"
    configured = True

    async def get_quote(self, symbol: str) -> Quote:
        timestamp = datetime.now(timezone.utc)
        return Quote(
            symbol=symbol,
            provider_symbol=symbol,
            price=100.0,
            timestamp=timestamp,
            provider_timestamp=timestamp,
            observed_at=timestamp,
            source=self.name,
            status=QuoteStatus.LIVE,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
            completeness_status=CompletenessStatus.COMPLETE,
        )


class FailingProvider(FakeProvider):
    name = "failing_provider"

    async def get_quote(self, symbol: str) -> Quote:
        raise RuntimeError("provider timeout")


def test_health_probe_marks_real_validated_response_operational() -> None:
    service = MarketDataHealthService()
    result = asyncio.run(service._run_quote_probe("primary", FakeProvider(), "BTC/USD"))

    assert result.status == "OPERATIONAL"
    assert result.validation_status == "PASSED"
    assert result.provenance_available is True
    assert result.last_successful_request is not None


def test_health_probe_does_not_mark_failed_provider_operational() -> None:
    service = MarketDataHealthService()
    result = asyncio.run(service._run_quote_probe("primary", FailingProvider(), "BTC/USD"))

    assert result.status == "UNAVAILABLE"
    assert result.validation_status == "FAILED"
    assert result.last_successful_request is None


def test_market_data_preference_defaults_are_strict() -> None:
    from app.preferences.models import default_preferences
    from app.preferences.schemas import UserPreferences

    preferences = UserPreferences.model_validate(default_preferences())
    market_data = preferences.market_data_preferences

    assert market_data.maximum_data_age_seconds == 30
    assert market_data.reject_stale_data is True
    assert market_data.require_completed_candles is True
    assert market_data.allow_cached_data_fallback is True
