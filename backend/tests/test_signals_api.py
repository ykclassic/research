from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api import signals
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
