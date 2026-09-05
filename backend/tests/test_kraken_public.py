from datetime import datetime, timezone

import pytest

from app.models.market import Timeframe
from app.providers.kraken_public import KrakenPublicProvider


def test_kraken_public_is_credential_free_and_supports_mtf_intervals() -> None:
    provider = KrakenPublicProvider()
    assert provider.configured is True
    assert provider._provider_pair("BTC/USD") == "XBTUSD"
    assert provider._provider_pair("ETH/USD") == "ETHUSD"
    assert provider._provider_pair("SOL/USD") == "SOLUSD"
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
        # The provider validates the range before making a network request.
        import asyncio
        asyncio.run(provider.get_candles("BTC/USD", Timeframe.HOUR_1, 100, start_date=start, end_date=end))
