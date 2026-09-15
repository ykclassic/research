from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.services.market_data_health import HealthProbe, MarketDataHealthService


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
        )

    async def get_candles(self, symbol: str, timeframe: Timeframe, outputsize: int = 50) -> OHLCVDataset:
        timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        candles = tuple(
            Candle(
                timestamp=timestamp - timedelta(hours=2 - index),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1.0,
                symbol=symbol,
                timeframe=timeframe,
                source=self.name,
                is_complete=True,
            )
            for index in range(3)
        )
        return OHLCVDataset(
            symbol=symbol,
            timeframe=timeframe,
            source=self.name,
            requested_at=datetime.now(timezone.utc),
            provider_timestamp=candles[-1].timestamp,
            candles=candles,
            completeness_status=CompletenessStatus.COMPLETE,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
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
    assert result.candle_completeness == "PASSED"
    assert result.provenance_available is True
    assert result.last_successful_request is not None


def test_health_probe_does_not_mark_failed_provider_operational() -> None:
    service = MarketDataHealthService()
    result = asyncio.run(service._run_quote_probe("primary", FailingProvider(), "BTC/USD"))

    assert result.status == "UNAVAILABLE"
    assert result.validation_status == "FAILED"
    assert result.last_successful_request is None


def test_market_health_serialization_uses_service_cache_configuration() -> None:
    service = MarketDataHealthService()
    checked_at = datetime.now(timezone.utc)
    probe = HealthProbe(
        role="primary",
        provider="fake_provider",
        status="OPERATIONAL",
        configured=True,
        last_successful_request=checked_at,
        last_request=checked_at,
        latency_ms=25,
        validation_status="PASSED",
        candle_completeness="PASSED",
        provenance_available=True,
        fallback_status="NOT_USED",
        cache_status="AVAILABLE",
        message="ok",
    )

    result = service._serialize({"primary": probe}, cached=False)

    assert result["cache_ttl_seconds"] == service.CACHE_SECONDS
    assert result["cached_result"] is False
    assert result["providers"][0]["provider"] == "fake_provider"
    assert result["security"]["credentials_exposed"] is False


def test_market_data_preference_defaults_are_strict() -> None:
    from app.preferences.models import default_preferences
    from app.preferences.schemas import UserPreferences

    preferences = UserPreferences.model_validate(default_preferences())
    market_data = preferences.market_data_preferences

    assert market_data.maximum_data_age_seconds == 30
    assert market_data.reject_stale_data is True
    assert market_data.require_completed_candles is True
    assert market_data.allow_cached_data_fallback is True
