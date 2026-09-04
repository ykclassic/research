from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.orchestrator import MarketDataOrchestrator
from app.services.market_sessions import is_market_open


class SemanticFakeProvider(MarketDataProvider):
    def __init__(self, name: str, quote: Quote) -> None:
        self.name = name
        self.quote = quote
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def get_quote(self, internal_symbol: str) -> Quote:
        self.calls += 1
        return self.quote.model_copy(update={"symbol": internal_symbol})

    async def get_candles(
        self,
        internal_symbol: str,
        timeframe: Timeframe,
        outputsize: int = 250,
        start_date=None,
        end_date=None,
    ):
        raise NotImplementedError


def stale_quote(symbol: str = "AAPL") -> Quote:
    timestamp = datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc)
    return Quote(
        symbol=symbol,
        provider_symbol=symbol,
        price=100.0,
        timestamp=timestamp,
        provider_timestamp=timestamp,
        observed_at=datetime(2026, 9, 4, 5, 30, tzinfo=timezone.utc),
        source="twelve_data",
        status=QuoteStatus.STALE,
        freshness_status=FreshnessStatus.STALE,
        freshness_age_seconds=34200,
        completeness_status=CompletenessStatus.COMPLETE,
    )


@pytest.mark.asyncio
async def test_market_closed_quote_is_not_a_provider_failure(monkeypatch):
    monkeypatch.setattr(settings, "provider_failure_threshold", 2)
    provider = SemanticFakeProvider("twelve_data", stale_quote())
    orchestrator = MarketDataOrchestrator([provider])
    monkeypatch.setattr("app.providers.orchestrator.is_market_open", lambda symbol: False)

    quote = await orchestrator.get_quote("AAPL", force_refresh=True)

    assert quote.status == QuoteStatus.MARKET_CLOSED
    assert quote.market_open is False
    assert quote.price == 100.0
    assert quote.error_code is None
    assert orchestrator.provider_status()[0].consecutive_failures == 0
    assert orchestrator.provider_status()[0].circuit_open is False


@pytest.mark.asyncio
async def test_stale_quote_during_open_market_is_not_a_provider_failure(monkeypatch):
    provider = SemanticFakeProvider("twelve_data", stale_quote())
    orchestrator = MarketDataOrchestrator([provider])
    monkeypatch.setattr("app.providers.orchestrator.is_market_open", lambda symbol: True)

    quote = await orchestrator.get_quote("AAPL", force_refresh=True)

    assert quote.status == QuoteStatus.STALE
    assert quote.market_open is True
    assert quote.error_code is None
    assert orchestrator.provider_status()[0].consecutive_failures == 0
    assert orchestrator.provider_status()[0].circuit_open is False


@pytest.mark.asyncio
async def test_real_provider_failure_still_advances_circuit(monkeypatch):
    class FailingProvider(SemanticFakeProvider):
        async def get_quote(self, internal_symbol: str) -> Quote:
            self.calls += 1
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(settings, "provider_failure_threshold", 2)
    failing = FailingProvider("twelve_data", stale_quote())
    orchestrator = MarketDataOrchestrator([failing])

    for _ in range(2):
        quote = await orchestrator.get_quote("AAPL", force_refresh=True)
        assert quote.status == QuoteStatus.UNAVAILABLE

    status = orchestrator.provider_status()[0]
    assert status.consecutive_failures == 2
    assert status.circuit_open is True


def test_market_session_semantics_are_deterministic():
    friday_pre_open = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    friday_regular = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
    friday_after_close = datetime(2026, 9, 4, 21, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)

    assert not is_market_open("AAPL", at=friday_pre_open)
    assert is_market_open("AAPL", at=friday_regular)
    assert not is_market_open("AAPL", at=friday_after_close)
    assert not is_market_open("AAPL", at=saturday)
    assert is_market_open("BTC/USD", at=saturday)
