from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import Candle, Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.orchestrator import MarketDataOrchestrator


class QuotaProvider(MarketDataProvider):
    name = "twelve_data"

    def __init__(self) -> None:
        self.quote_calls: list[list[str]] = []
        self.candle_calls: list[Timeframe] = []

    @property
    def configured(self) -> bool:
        return True

    async def get_quotes(self, internal_symbols: list[str]) -> list[Quote]:
        self.quote_calls.append(list(internal_symbols))
        now = datetime.now(timezone.utc)
        return [Quote(
            symbol=symbol,
            provider_symbol=symbol,
            price=100.0,
            timestamp=now,
            provider_timestamp=now,
            observed_at=now,
            source=self.name,
            status=QuoteStatus.LIVE,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
        ) for symbol in internal_symbols]

    async def get_candles(self, internal_symbol: str, timeframe: Timeframe, outputsize: int = 250, start_date=None, end_date=None) -> OHLCVDataset:
        self.candle_calls.append(timeframe)
        now = datetime.now(timezone.utc)
        candles = tuple(Candle(
            timestamp=now - timedelta(seconds=timeframe.seconds * (29 - index)),
            open=99.0,
            high=101.0,
            low=98.0,
            close=100.0,
            volume=1.0,
            symbol=internal_symbol,
            timeframe=timeframe,
            source=self.name,
            is_complete=True,
        ) for index in range(30))
        return OHLCVDataset(
            symbol=internal_symbol,
            timeframe=timeframe,
            source=self.name,
            requested_at=now,
            provider_timestamp=candles[-1].timestamp,
            candles=candles,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
            completeness_status=CompletenessStatus.COMPLETE,
        )


@pytest.mark.asyncio
async def test_quote_budget_cannot_consume_mtf_candle_reserve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "twelve_data_quote_minute_budget", 4)
    monkeypatch.setattr(settings, "twelve_data_candle_minute_reserve", 4)
    provider = QuotaProvider()
    orchestrator = MarketDataOrchestrator([provider])

    quotes = await orchestrator.get_quotes(["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY"], force_refresh=True)
    assert len(quotes) == 6
    assert provider.quote_calls == [["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD"]]

    for timeframe in (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15):
        dataset = await orchestrator.get_candles("BTC/USD", timeframe, 30)
        assert dataset.source == "twelve_data"

    assert provider.candle_calls == [Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15]


@pytest.mark.asyncio
async def test_candle_quota_exhaustion_routes_to_fallback_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "twelve_data_quote_minute_budget", 4)
    monkeypatch.setattr(settings, "twelve_data_candle_minute_reserve", 4)
    twelve = QuotaProvider()
    fallback = QuotaProvider()
    fallback.name = "finnhub"
    orchestrator = MarketDataOrchestrator([twelve, fallback])

    await orchestrator.get_quotes(["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD"], force_refresh=True)
    for timeframe in (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15):
        await orchestrator.get_candles("BTC/USD", timeframe, 30)

    assert len(twelve.candle_calls) == 4
    assert len(fallback.candle_calls) == 0
