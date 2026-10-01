from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api import signal_outcomes


def _record(provider: str) -> SimpleNamespace:
    return SimpleNamespace(
        provider=provider,
        symbol="SUI/USDT" if provider == "kraken_public_cross" else "BTC/USDT",
        dispatched_at=datetime(2026, 9, 27, 14, 48, 29, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_cross_provider_outcome_uses_kraken_cross_historical_route(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeKraken:
        async def get_cross_candles(self, symbol, timeframe, outputsize, **kwargs):
            calls.append(("cross", symbol))
            return SimpleNamespace(source="kraken_public_cross", completed_candles=())

        async def get_candles(self, *args, **kwargs):
            raise AssertionError("Native Kraken route must not be used for cross provenance.")

    class FakeOrchestrator:
        async def get_candles(self, *args, **kwargs):
            raise AssertionError("Canonical orchestrator must not be used for cross provenance.")

    monkeypatch.setattr(signal_outcomes, "kraken_public", FakeKraken())
    monkeypatch.setattr(
        signal_outcomes.quote_service,
        "orchestrator",
        FakeOrchestrator(),
    )

    dataset = await signal_outcomes._historical_candles(
        _record("kraken_public_cross")
    )

    assert calls == [("cross", "SUI/USDT")]
    assert dataset.source == "kraken_public_cross"


@pytest.mark.asyncio
async def test_native_kraken_provider_keeps_native_historical_route(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeKraken:
        async def get_candles(self, symbol, timeframe, outputsize, **kwargs):
            calls.append(("native", symbol))
            return SimpleNamespace(source="kraken_public", completed_candles=())

        async def get_cross_candles(self, *args, **kwargs):
            raise AssertionError("Cross route must not be used for native Kraken provenance.")

    class FakeOrchestrator:
        async def get_candles(self, *args, **kwargs):
            raise AssertionError("Canonical orchestrator must not be used for native Kraken provenance.")

    monkeypatch.setattr(signal_outcomes, "kraken_public", FakeKraken())
    monkeypatch.setattr(
        signal_outcomes.quote_service,
        "orchestrator",
        FakeOrchestrator(),
    )

    dataset = await signal_outcomes._historical_candles(_record("kraken_public"))

    assert calls == [("native", "BTC/USDT")]
    assert dataset.source == "kraken_public"


@pytest.mark.asyncio
async def test_cross_provider_rejects_mismatched_observation_source(monkeypatch):
    class FakeKraken:
        async def get_cross_candles(self, *args, **kwargs):
            return SimpleNamespace(source="twelve_data", completed_candles=())

    monkeypatch.setattr(signal_outcomes, "kraken_public", FakeKraken())

    with pytest.raises(RuntimeError, match="Outcome audit provenance mismatch"):
        await signal_outcomes._historical_candles(
            _record("kraken_public_cross")
        )
