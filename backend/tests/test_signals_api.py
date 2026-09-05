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
        confluence=0.65,
        price=100.0,
        calculated_at=now,
        latest_candle_timestamp=now,
        source="test",
        components=(),
        evidence=("test",),
    )


@pytest.mark.asyncio
async def test_signal_scanner_contains_only_registered_crypto_symbols(monkeypatch):
    monkeypatch.setattr(signals, "_generate", lambda symbol, limit: _fake_signal(symbol))
    result = await signals.get_crypto_signals(limit=30, user=None)
    assert [item.symbol for item in result.signals] == ["BTC/USD", "ETH/USD", "SOL/USD"]


@pytest.mark.asyncio
async def test_signal_endpoint_rejects_non_crypto_symbol():
    with pytest.raises(HTTPException) as exc:
        await signals.get_crypto_signal("EUR/USD", limit=30, user=None)
    assert exc.value.status_code == 422
    assert "crypto pairs only" in str(exc.value.detail)
