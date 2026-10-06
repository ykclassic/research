from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.orchestrator import MarketDataOrchestrator
from app.services import signal_candle_scheduler as scheduler_service
from app.services.signal_candle_scheduler import SignalCandleScheduler


def _dataset(symbol: str, timeframe: Timeframe, source: str = "test") -> OHLCVDataset:
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=timeframe.seconds * 40)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(seconds=timeframe.seconds * index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            is_complete=True,
        )
        for index in range(40)
    )
    return OHLCVDataset(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        requested_at=now,
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
        request_latency_ms=1,
        freshness_status=FreshnessStatus.FRESH,
        freshness_age_seconds=0.0,
        completeness_status=CompletenessStatus.COMPLETE,
    )


class _FakeOrchestrator:
    def __init__(self, providers: int = 3) -> None:
        self.providers = [object() for _ in range(providers)]
        self.calls: list[dict[str, object]] = []

    async def get_candles(self, symbol, timeframe, outputsize, **kwargs):
        self.calls.append({"symbol": symbol, "timeframe": timeframe, **kwargs})
        return _dataset(symbol, timeframe)


class _FakeQuoteService:
    def __init__(self, orchestrator) -> None:
        self.orchestrator = orchestrator


class _SlowKraken:
    def __init__(self, delay: float, *, result: bool = True) -> None:
        self.delay = delay
        self.result = result
        self.calls = 0

    async def get_candles(self, symbol, timeframe, outputsize):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if not self.result:
            raise RuntimeError("kraken unavailable")
        return _dataset(symbol, timeframe, "kraken_public")


class _NamedProvider(MarketDataProvider):
    def __init__(self, name: str, delay: float = 0.0, fail: bool = False) -> None:
        self.name = name
        self.delay = delay
        self.fail = fail
        self.calls = 0

    @property
    def configured(self) -> bool:
        return True

    async def get_quote(self, internal_symbol: str):
        raise NotImplementedError

    async def get_candles(self, internal_symbol, timeframe, outputsize=250, start_date=None, end_date=None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError(f"{self.name} unavailable")
        return _dataset(internal_symbol, timeframe, self.name)


@pytest.mark.asyncio
async def test_kraken_slow_but_successful_is_not_cancelled_by_old_short_budget(monkeypatch):
    provider = _SlowKraken(0.03)
    service = _FakeQuoteService(_FakeOrchestrator())
    scheduler = SignalCandleScheduler(service, provider)
    monkeypatch.setattr(scheduler, "PRIMARY_TIMEOUT_SECONDS", 0.10)

    started = asyncio.get_running_loop().time()
    dataset = await scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250)
    elapsed = asyncio.get_running_loop().time() - started

    assert dataset.source == "kraken_public"
    assert provider.calls == 1
    assert elapsed >= 0.03


@pytest.mark.asyncio
async def test_kraken_timeout_falls_back_with_cumulative_budget(monkeypatch):
    provider = _SlowKraken(0.10)
    orchestrator = _FakeOrchestrator(providers=3)
    service = _FakeQuoteService(orchestrator)
    scheduler = SignalCandleScheduler(service, provider)
    monkeypatch.setattr(scheduler, "PRIMARY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(scheduler, "FALLBACK_PROVIDER_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(scheduler, "FALLBACK_BUDGET_MARGIN_SECONDS", 0.02)

    dataset = await scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250)

    assert dataset.source == "test"
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["provider_timeout_seconds"] == 0.02


@pytest.mark.asyncio
async def test_kraken_timeout_twelve_data_slow_finnhub_succeeds(monkeypatch):
    kraken = _SlowKraken(0.10)
    twelve = _NamedProvider("twelve_data", delay=0.06)
    finnhub = _NamedProvider("finnhub", delay=0.01)
    orchestrator = MarketDataOrchestrator([twelve, finnhub])
    scheduler = SignalCandleScheduler(_FakeQuoteService(orchestrator), kraken)

    monkeypatch.setattr(scheduler, "PRIMARY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(scheduler, "FALLBACK_PROVIDER_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(scheduler, "FALLBACK_BUDGET_MARGIN_SECONDS", 0.03)

    dataset = await scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250)

    assert dataset.source == "finnhub"
    assert dataset.fallback_used is True
    assert twelve.calls == 1
    assert finnhub.calls == 1
    assert dataset.provider_attempts == ("twelve_data", "finnhub")


@pytest.mark.asyncio
async def test_all_candle_providers_unavailable_returns_clean_failure(monkeypatch):
    kraken = _SlowKraken(0.01, result=False)
    twelve = _NamedProvider("twelve_data", fail=True)
    finnhub = _NamedProvider("finnhub", fail=True)
    alpha = _NamedProvider("alpha_vantage", fail=True)
    orchestrator = MarketDataOrchestrator([twelve, finnhub, alpha])
    scheduler = SignalCandleScheduler(_FakeQuoteService(orchestrator), kraken)

    monkeypatch.setattr(scheduler, "PRIMARY_TIMEOUT_SECONDS", 0.005)
    monkeypatch.setattr(scheduler, "FALLBACK_PROVIDER_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(scheduler, "FALLBACK_BUDGET_MARGIN_SECONDS", 0.02)

    with pytest.raises(RuntimeError, match="fallback budget"):
        await scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250)


@pytest.mark.asyncio
async def test_five_timeframes_remain_sequential_and_complete_within_overall_budget():
    provider = _SlowKraken(0.01)
    scheduler = SignalCandleScheduler(_FakeQuoteService(_FakeOrchestrator()), provider)

    started = asyncio.get_running_loop().time()
    datasets = await scheduler.get_required_datasets(
        "BTC/USDT",
        (
            Timeframe.DAY_1,
            Timeframe.HOUR_4,
            Timeframe.HOUR_1,
            Timeframe.MINUTE_15,
            Timeframe.MINUTE_5,
        ),
        250,
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert tuple(datasets) == (
        Timeframe.DAY_1,
        Timeframe.HOUR_4,
        Timeframe.HOUR_1,
        Timeframe.MINUTE_15,
        Timeframe.MINUTE_5,
    )
    assert provider.calls == 5
    assert elapsed < SignalCandleScheduler.OVERALL_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_enhanced_signal_503_does_not_expose_provider_diagnostics(monkeypatch):
    from app.api import enhanced_signals

    class Record:
        pass

    record = Record()
    record.enabled_symbols = {"BTC/USDT"}

    monkeypatch.setattr(enhanced_signals, "require_feature", lambda *args, **kwargs: None)
    monkeypatch.setattr(enhanced_signals.preferences_service, "get_or_create", lambda *args, **kwargs: record)
    monkeypatch.setattr(
        enhanced_signals,
        "market_coverage",
        lambda value: type("Coverage", (), {"enabled_symbols": {"BTC/USDT"}})(),
    )

    async def fail(*args, **kwargs):
        raise RuntimeError("Kraken secret provider diagnostics must stay server-side")

    monkeypatch.setattr(enhanced_signals.scheduler, "get_required_datasets", fail)

    user = type("User", (), {"id": "user"})()
    with pytest.raises(HTTPException) as exc:
        await enhanced_signals.get_enhanced_signal(
            "BTC/USDT",
            user=user,
            limit=250,
            access_token="token",
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "Enhanced Signal is temporarily unavailable. Please retry shortly."
    assert "Kraken secret" not in exc.value.detail


@pytest.mark.asyncio
async def test_production_verification_serializes_enhanced_signal_check_count(monkeypatch):
    from types import SimpleNamespace

    from app.api import enhanced_signals

    datasets = {
        timeframe: SimpleNamespace(source="kraken_public", cache_hit=False)
        for timeframe in enhanced_signals.REQUIRED
    }

    async def get_required_datasets(*args, **kwargs):
        return datasets

    class News:
        fundamental_events = ()
        news = ()

    monkeypatch.setattr(
        enhanced_signals.scheduler,
        "get_required_datasets",
        get_required_datasets,
    )
    monkeypatch.setattr(
        enhanced_signals.news_research,
        "research",
        lambda **kwargs: News(),
    )
    monkeypatch.setattr(
        enhanced_signals,
        "generate_enhanced_signal",
        lambda *args, **kwargs: (
            SimpleNamespace(
                qualification_status="WAIT",
                research_eligible=False,
            ),
            SimpleNamespace(
                evidence=(object(), object(), object()),
            ),
        ),
    )

    payload = await enhanced_signals.verify_enhanced_signal_production(
        "BTC/USDT",
        None,
        limit=250,
    )

    assert payload["status"] == "ok"
    assert payload["checks"] == 3
