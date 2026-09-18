from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncio

import pytest
from fastapi import HTTPException

from app.api import signals
from app.services import signal_candle_scheduler as scheduler_service
from app.models.signal import CryptoSignal, SignalDirection


def _fake_signal(symbol: str) -> CryptoSignal:
    now = datetime.now(timezone.utc)
    return CryptoSignal(
        symbol=symbol,
        signal=SignalDirection.BUY,
        score=0.30,
        confidence=0.65,
        confluence=0.65,
        risk_reward=2.0,
        price=100.0,
        calculated_at=now,
        latest_candle_timestamp=now,
        source="test",
        components=(),
        evidence=("test",),
        research_eligible=True,
        qualification_reasons=(),
    )


@pytest.mark.asyncio
async def test_signal_scanner_keeps_legacy_crypto_collection(monkeypatch):
    async def fake_generate(
        symbol: str,
        limit: int,
        signal_preferences: dict[str, object] | None = None,
        policy=None,
    ) -> CryptoSignal:
        return _fake_signal(symbol)

    monkeypatch.setattr(signals, "_generate", fake_generate)
    result = await signals.get_crypto_signals(limit=30, user=None)
    assert [item.symbol for item in result.signals] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


@pytest.mark.asyncio
async def test_selected_signal_allows_supported_enabled_class(monkeypatch):
    async def fake_generate(
        symbol: str,
        limit: int,
        signal_preferences: dict[str, object] | None = None,
        policy=None,
    ) -> CryptoSignal:
        return _fake_signal(symbol)

    monkeypatch.setattr(signals, "_generate", fake_generate)
    result = await signals.get_crypto_signal("EURUSD", limit=30, user=None)
    assert result.symbol == "EURUSD"


@pytest.mark.asyncio
async def test_selected_signal_rejects_non_enabled_user_symbol(monkeypatch):
    class Record:
        id = "record"
        signal_preferences = {}
        market_data_preferences = {}

    class FakePreferences:
        def get_or_create(self, access_token, user_id):
            return Record()

    monkeypatch.setattr(signals, "preferences_service", FakePreferences())
    monkeypatch.setattr(signals, "market_coverage", lambda record: type("Coverage", (), {"enabled_symbols": {"EURUSD"}})())
    monkeypatch.setattr(signals, "_generate", lambda *args, **kwargs: _fake_signal("BTC/USDT"))

    user = type("User", (), {"id": "user"})()
    with pytest.raises(HTTPException) as exc:
        await signals.get_crypto_signal("BTC/USDT", limit=30, user=user, access_token="token")
    assert exc.value.status_code == 404
    assert "not enabled" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_selected_signal_falls_back_when_primary_exceeds_signal_budget(monkeypatch):
    calls = []

    async def slow_primary(symbol, timeframe, limit):
        calls.append(("primary", timeframe))
        await asyncio.sleep(1)

    async def fallback(symbol, timeframe, limit):
        calls.append(("fallback", timeframe))
        return _dataset(symbol, timeframe)

    monkeypatch.setattr(
        scheduler_service.SignalCandleScheduler,
        "PRIMARY_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        scheduler_service.SignalCandleScheduler,
        "FALLBACK_TIMEOUT_SECONDS",
        0.2,
    )
    monkeypatch.setattr(signals.kraken_public, "get_candles", slow_primary)
    monkeypatch.setattr(signals.quote_service.orchestrator, "get_candles", fallback)
    monkeypatch.setattr(
        scheduler_service,
        "require_current_completed_candles",
        lambda dataset: dataset,
    )
    monkeypatch.setattr(
        signals,
        "generate_crypto_signal",
        lambda datasets, preferences: _fake_signal(datasets[signals.Timeframe.DAY_1].symbol),
    )

    result = await signals._generate("BTC/USDT", 30)
    assert result.symbol == "BTC/USDT"
    assert {timeframe for _, timeframe in calls} == set(signals.REQUIRED_TIMEFRAMES)
    assert sum(kind == "primary" for kind, _ in calls) == len(signals.REQUIRED_TIMEFRAMES)
    assert sum(kind == "fallback" for kind, _ in calls) == len(signals.REQUIRED_TIMEFRAMES)


def _dataset(symbol: str, timeframe: signals.Timeframe):
    from app.models.market import Candle, OHLCVDataset

    now = datetime.now(timezone.utc)
    candles = tuple(
        Candle(
            timestamp=now - timedelta(seconds=30 - index),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
            symbol=symbol,
            timeframe=timeframe,
            source="test",
            is_complete=True,
        )
        for index in range(30)
    )
    return OHLCVDataset(
        symbol=symbol,
        timeframe=timeframe,
        source="test",
        requested_at=now,
        provider_timestamp=now,
        candles=candles,
    )
