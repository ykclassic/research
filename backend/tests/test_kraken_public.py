from datetime import datetime, timezone

import pytest

from app.models.market import Timeframe
from app.providers.kraken_public import KrakenPublicProvider


def test_kraken_public_is_credential_free_and_supports_expanded_crypto_universe() -> None:
    provider = KrakenPublicProvider()
    assert provider.configured is True
    expected = {
        "BTC/USDT": "XBTUSDT",
        "ETH/USDT": "ETHUSDT",
        "BNB/USDT": "BNBUSDT",
        "XRP/USDT": "XRPUSDT",
        "LINK/USDT": "LINKUSDT",
        "SOL/USDT": "SOLUSDT",
        "DOGE/USDT": "DOGEUSDT",
        "ADA/USDT": "ADAUSDT",
        "SUI/USDT": "SUIUSDT",
        "LTC/USDT": "LTCUSDT",
        "BTC/USD": "XBTUSD",
        "ETH/USD": "ETHUSD",
        "SOL/USD": "SOLUSD",
    }
    assert {symbol: provider._provider_pair(symbol) for symbol in expected} == expected
    assert provider._intervals == {
        Timeframe.MINUTE_15: 15,
        Timeframe.HOUR_1: 60,
        Timeframe.HOUR_4: 240,
        Timeframe.DAY_1: 1440,
    }


def test_kraken_public_rejects_non_crypto_symbols() -> None:
    provider = KrakenPublicProvider()
    with pytest.raises(ValueError, match="does not support forex"):
        provider._provider_pair("EUR/USD")


def test_kraken_public_rejects_invalid_historical_range() -> None:
    provider = KrakenPublicProvider()
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="start_date must be before end_date"):
        import asyncio
        asyncio.run(provider.get_candles("BTC/USD", Timeframe.HOUR_1, 100, start_date=start, end_date=end))


def test_kraken_public_candle_cache_is_shared_across_provider_instances(monkeypatch) -> None:
    import asyncio

    KrakenPublicProvider._candle_cache.clear()
    calls = 0
    base = int(datetime.now(timezone.utc).timestamp()) - 3600

    async def fake_request_json(self, endpoint, params, timeout_seconds):
        nonlocal calls
        calls += 1
        rows = []
        for index in range(40):
            timestamp = base - (39 - index) * 3600
            price = 100.0 + index
            rows.append([timestamp, price - 0.5, price + 0.5, price - 1.0, price, "0", "10"])
        return {"result": {"XBTUSD": rows, "last": str(base)}}

    monkeypatch.setattr(KrakenPublicProvider, "_request_json", fake_request_json)
    first = asyncio.run(KrakenPublicProvider().get_candles("BTC/USD", Timeframe.HOUR_1, 40))
    second = asyncio.run(KrakenPublicProvider().get_candles("BTC/USD", Timeframe.HOUR_1, 40))

    assert calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.request_latency_ms == 0
    assert second.candles == first.candles
