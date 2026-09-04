from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider, ProviderUsage
from app.providers.errors import ProviderErrorCode
from app.providers.orchestrator import MarketDataOrchestrator
from app.services.quota_scheduler import QuoteQuotaScheduler


class FakeProvider(MarketDataProvider):
    def __init__(self, name: str, *, remaining: int | None = None) -> None:
        self.name = name
        self.calls: list[list[str]] = []
        self._remaining = remaining

    @property
    def configured(self) -> bool:
        return True

    @property
    def usage(self) -> ProviderUsage | None:
        if self._remaining is None:
            return None
        return ProviderUsage(credits_used=8 - self._remaining, credits_remaining=self._remaining, observed_at=datetime.now(timezone.utc))

    async def get_quote(self, internal_symbol: str) -> Quote:
        self.calls.append([internal_symbol])
        return Quote(symbol=internal_symbol, provider_symbol=internal_symbol, price=100.0, source=self.name, status=QuoteStatus.LIVE)

    async def get_quotes(self, internal_symbols: list[str]) -> list[Quote]:
        self.calls.append(list(internal_symbols))
        return [Quote(symbol=s, provider_symbol=s, price=100.0, source=self.name, status=QuoteStatus.LIVE) for s in internal_symbols]

    async def get_candles(self, internal_symbol: str, timeframe: Timeframe, outputsize: int = 250, start_date=None, end_date=None) -> OHLCVDataset:
        raise NotImplementedError


def test_scheduler_uses_configured_minute_and_daily_capacity() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=6, daily_budget=8)
    assert scheduler.reserve(10) == 6
    assert scheduler.snapshot().minute_remaining == 0
    assert scheduler.snapshot().daily_remaining == 2


def test_scheduler_clamps_to_recent_provider_telemetry() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=6, daily_budget=800)
    scheduler.observe_provider_remaining(2, datetime.now(timezone.utc))
    assert scheduler.snapshot().available == 2
    assert scheduler.reserve(10) == 2


def test_scheduler_ignores_stale_provider_telemetry() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=6, daily_budget=800)
    scheduler.observe_provider_remaining(1, datetime.now(timezone.utc) - timedelta(seconds=61))
    assert scheduler.snapshot().provider_remaining is None
    assert scheduler.snapshot().available == 6


@pytest.mark.asyncio
async def test_scheduler_reserves_actual_capacity_and_routes_overflow_to_finnhub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "twelve_data_quote_minute_budget", 6)
    monkeypatch.setattr(settings, "twelve_data_quote_daily_budget", 800)
    twelve, finnhub, alpha = FakeProvider("twelve_data"), FakeProvider("finnhub"), FakeProvider("alpha_vantage")
    orchestrator = MarketDataOrchestrator([alpha, twelve, finnhub])
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"]

    quotes = await orchestrator.get_quotes(symbols, force_refresh=True)

    assert twelve.calls == [symbols[:6]]
    assert finnhub.calls == [symbols[6:]]
    assert alpha.calls == []
    assert len(quotes) == len(symbols)


@pytest.mark.asyncio
async def test_provider_reported_remaining_credits_controls_next_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "twelve_data_quote_minute_budget", 6)
    monkeypatch.setattr(settings, "twelve_data_quote_daily_budget", 800)
    twelve, finnhub, alpha = FakeProvider("twelve_data", remaining=2), FakeProvider("finnhub"), FakeProvider("alpha_vantage")
    orchestrator = MarketDataOrchestrator([twelve, alpha, finnhub])
    orchestrator._twelve_data_quota.observe_provider_remaining(2, datetime.now(timezone.utc))
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD"]

    quotes = await orchestrator.get_quotes(symbols, force_refresh=True)

    assert twelve.calls == [symbols[:2]]
    assert finnhub.calls == [symbols[2:]]
    assert alpha.calls == []
    assert all(q.status == QuoteStatus.LIVE for q in quotes)


@pytest.mark.asyncio
async def test_daily_exhaustion_routes_without_dispatching_twelve_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "twelve_data_quote_minute_budget", 6)
    monkeypatch.setattr(settings, "twelve_data_quote_daily_budget", 1)
    twelve, finnhub, alpha = FakeProvider("twelve_data"), FakeProvider("finnhub"), FakeProvider("alpha_vantage")
    orchestrator = MarketDataOrchestrator([twelve, alpha, finnhub])
    assert orchestrator._twelve_data_quota.reserve(1) == 1
    symbols = ["BTC/USD", "ETH/USD"]

    quotes = await orchestrator.get_quotes(symbols, force_refresh=True)

    assert twelve.calls == []
    assert finnhub.calls == [symbols]
    assert alpha.calls == []
    assert all(q.status == QuoteStatus.LIVE for q in quotes)
    status = next(item for item in orchestrator.provider_status() if item.provider == "twelve_data")
    assert status.last_error_code == ProviderErrorCode.QUOTA_EXHAUSTED
    assert status.daily_quote_budget_remaining == 0
