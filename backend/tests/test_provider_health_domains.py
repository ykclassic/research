from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models import Candle, Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.errors import ProviderErrorCode
from app.providers.orchestrator import MarketDataOrchestrator


class DomainHealthProvider(MarketDataProvider):
    name = "twelve_data"

    def __init__(self, *, quote_fails: bool = False, candle_fails: bool = False) -> None:
        self.quote_fails = quote_fails
        self.candle_fails = candle_fails
        self.quote_calls = 0
        self.candle_calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def get_quote(self, internal_symbol: str) -> Quote:
        self.quote_calls += 1
        if self.quote_fails:
            raise RuntimeError("quote upstream unavailable")
        now = datetime.now(timezone.utc)
        return Quote(
            symbol=internal_symbol, provider_symbol=internal_symbol, price=100.0,
            timestamp=now, provider_timestamp=now, observed_at=now, source=self.name,
            status=QuoteStatus.LIVE, freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
        )

    async def get_candles(self, internal_symbol: str, timeframe: Timeframe, outputsize: int = 250, start_date=None, end_date=None) -> OHLCVDataset:
        self.candle_calls += 1
        if self.candle_fails:
            raise RuntimeError("candle upstream unavailable")
        now = datetime.now(timezone.utc)
        candle = Candle(
            timestamp=now, open=99.0, high=101.0, low=98.0, close=100.0,
            volume=10.0, symbol=internal_symbol, timeframe=timeframe,
            source=self.name, is_complete=True,
        )
        return OHLCVDataset(
            symbol=internal_symbol, timeframe=timeframe, source=self.name,
            requested_at=now, provider_timestamp=now, candles=(candle,),
            freshness_status=FreshnessStatus.FRESH, freshness_age_seconds=0.0,
            completeness_status=CompletenessStatus.COMPLETE,
        )


@pytest.mark.asyncio
async def test_quote_circuit_does_not_block_candle_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_failure_threshold", 1)
    provider = DomainHealthProvider(quote_fails=True)
    orchestrator = MarketDataOrchestrator([provider])

    quote = await orchestrator.get_quote("BTC/USD", force_refresh=True)
    assert quote.status == QuoteStatus.UNAVAILABLE

    quote_state = orchestrator._health[("twelve_data", "quote")]
    candle_state = orchestrator._health[("twelve_data", "candles")]
    assert quote_state.circuit_open is True
    assert quote_state.consecutive_failures == 1
    assert candle_state.circuit_open is False
    assert candle_state.consecutive_failures == 0

    candles = await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1)
    assert candles.source == "twelve_data"
    assert provider.candle_calls == 1
    assert orchestrator._health[("twelve_data", "candles")].consecutive_failures == 0


@pytest.mark.asyncio
async def test_candle_circuit_does_not_block_quote_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_failure_threshold", 1)
    provider = DomainHealthProvider(candle_fails=True)
    orchestrator = MarketDataOrchestrator([provider])

    with pytest.raises(RuntimeError, match="no canonical candle cache"):
        await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1)

    candle_state = orchestrator._health[("twelve_data", "candles")]
    quote_state = orchestrator._health[("twelve_data", "quote")]
    assert candle_state.circuit_open is True
    assert candle_state.consecutive_failures == 1
    assert quote_state.circuit_open is False
    assert quote_state.consecutive_failures == 0

    quote = await orchestrator.get_quote("BTC/USD", force_refresh=True)
    assert quote.status == QuoteStatus.LIVE
    assert provider.quote_calls == 1
    assert orchestrator._health[("twelve_data", "quote")].consecutive_failures == 0


@pytest.mark.asyncio
async def test_quote_and_candle_success_reset_only_their_own_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_failure_threshold", 2)
    provider = DomainHealthProvider(quote_fails=True, candle_fails=True)
    orchestrator = MarketDataOrchestrator([provider])

    await orchestrator.get_quote("BTC/USD", force_refresh=True)
    with pytest.raises(RuntimeError, match="no canonical candle cache"):
        await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1)
    assert orchestrator._health[("twelve_data", "quote")].consecutive_failures == 1
    assert orchestrator._health[("twelve_data", "candles")].consecutive_failures == 1

    provider.quote_fails = False
    provider.candle_fails = False
    quote = await orchestrator.get_quote("BTC/USD", force_refresh=True)
    candles = await orchestrator.get_candles("BTC/USD", Timeframe.HOUR_1)

    assert quote.status == QuoteStatus.LIVE
    assert candles.source == "twelve_data"
    assert orchestrator._health[("twelve_data", "quote")].consecutive_failures == 0
    assert orchestrator._health[("twelve_data", "candles")].consecutive_failures == 0


def test_all_provider_health_domains_exist() -> None:
    orchestrator = MarketDataOrchestrator([DomainHealthProvider()])
    assert set(orchestrator._health) == {
        ("twelve_data", "quote"),
        ("twelve_data", "candles"),
    }
    assert len(orchestrator.provider_status("quote")) == 1
    assert len(orchestrator.provider_status("candles")) == 1


@pytest.mark.asyncio
async def test_health_domains_remain_independent_after_quote_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_failure_threshold", 1)
    provider = DomainHealthProvider(quote_fails=True, candle_fails=False)
    orchestrator = MarketDataOrchestrator([provider])

    await orchestrator.get_quote("BTC/USD", force_refresh=True)
    candle_status = orchestrator.provider_status("candles")[0]
    quote_status = orchestrator.provider_status("quote")[0]

    assert quote_status.circuit_open is True
    assert quote_status.last_error_code == ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert candle_status.circuit_open is False
    assert candle_status.consecutive_failures == 0
