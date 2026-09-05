from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider, dataset_completeness
from app.services.candle_freshness import refresh_candle_freshness
from app.services.data_validation import validate_ohlcv_dataset
from app.symbols import normalize_symbol


class KrakenPublicProvider(MarketDataProvider):
    """Public Kraken spot market-data fallback for crypto research.

    Kraken's public market-data endpoints require no API credentials and expose
    native 15-minute, 1-hour, 4-hour, and daily OHLC intervals. The endpoint
    always includes the currently forming candle, so this provider explicitly
    removes incomplete candles before returning a dataset.
    """

    name = "kraken_public"
    base_url = "https://api.kraken.com/0/public"

    _intervals = {
        Timeframe.MINUTE_15: 15,
        Timeframe.HOUR_1: 60,
        Timeframe.HOUR_4: 240,
        Timeframe.DAY_1: 1440,
    }

    _pairs = {
        "BTC/USD": "XBTUSD",
        "ETH/USD": "ETHUSD",
        "SOL/USD": "SOLUSD",
    }

    @property
    def configured(self) -> bool:
        return True

    @property
    def supports_batch_quotes(self) -> bool:
        return False

    @staticmethod
    def _parse_pair_result(result: dict, pair: str) -> list[list]:
        rows = result.get(pair)
        if isinstance(rows, list):
            return rows
        for key, value in result.items():
            if key != "last" and isinstance(value, list):
                return value
        raise ValueError(f"Kraken returned no OHLC rows for {pair}.")

    def _provider_pair(self, internal_symbol: str) -> str:
        mapping = normalize_symbol(internal_symbol)
        if mapping.asset_class != "crypto":
            raise ValueError(f"Kraken public provider does not support {mapping.asset_class} symbols.")
        try:
            return self._pairs[mapping.internal]
        except KeyError as exc:
            raise ValueError(f"Kraken public provider does not support {mapping.internal}.") from exc

    async def get_quote(self, internal_symbol: str) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        pair = self._provider_pair(internal_symbol)
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            response = await client.get(f"{self.base_url}/Ticker", params={"pair": pair})
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise ValueError(f"Kraken ticker error: {payload['error']}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Kraken returned an invalid ticker response.")
        row = next((value for value in result.values() if isinstance(value, dict)), None)
        if row is None:
            raise ValueError("Kraken returned no ticker data.")
        price = float(row["c"][0])
        observed_at = datetime.now(timezone.utc)
        return Quote(
            symbol=mapping.internal,
            provider_symbol=pair,
            price=price,
            timestamp=observed_at,
            provider_timestamp=observed_at,
            observed_at=observed_at,
            source=self.name,
            status=QuoteStatus.LIVE,
            latency_ms=int((time.perf_counter() - started) * 1000),
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
            completeness_status=CompletenessStatus.COMPLETE,
            provider_attempts=(self.name,),
        )

    async def get_candles(
        self,
        internal_symbol: str,
        timeframe: Timeframe,
        outputsize: int = 250,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> OHLCVDataset:
        mapping = normalize_symbol(internal_symbol)
        if mapping.asset_class != "crypto":
            raise ValueError(f"Kraken public provider does not support {mapping.asset_class} symbols.")
        timeframe = Timeframe(timeframe)
        interval = self._intervals.get(timeframe)
        if interval is None:
            raise ValueError(f"Kraken public provider does not support {timeframe.value} candles.")
        if (start_date is None) != (end_date is None):
            raise ValueError("Historical candle ranges require both start_date and end_date.")
        if start_date is not None and end_date is not None and start_date >= end_date:
            raise ValueError("Historical candle start_date must be before end_date.")

        pair = self._provider_pair(internal_symbol)
        requested_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        params: dict[str, str] = {"pair": pair, "interval": str(interval)}
        if start_date is not None:
            params["since"] = str(int(start_date.timestamp()))

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(f"{self.base_url}/OHLC", params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise ValueError(f"Kraken OHLC error: {payload['error']}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Kraken returned an invalid OHLC response.")

        rows = self._parse_pair_result(result, pair)
        now = datetime.now(timezone.utc)
        candles: list[Candle] = []
        duration = timeframe.seconds
        for row in rows:
            if len(row) < 7:
                continue
            timestamp = datetime.fromtimestamp(float(row[0]), tz=timezone.utc)
            candles.append(
                Candle(
                    timestamp=timestamp,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[6]),
                    symbol=mapping.internal,
                    timeframe=timeframe,
                    source=self.name,
                    is_complete=timestamp.timestamp() + duration <= now.timestamp(),
                )
            )

        completed = [candle for candle in candles if candle.is_complete]
        if end_date is not None:
            completed = [candle for candle in completed if candle.timestamp < end_date.astimezone(timezone.utc)]
        completed = completed[-min(max(outputsize, 30), 720):]
        if len(completed) < 30:
            raise ValueError(
                f"Kraken returned only {len(completed)} completed {timeframe.value} candles; at least 30 are required."
            )

        provider_timestamp = completed[-1].timestamp
        provisional = OHLCVDataset.model_construct(
            symbol=mapping.internal,
            timeframe=timeframe,
            source=self.name,
            requested_at=requested_at,
            provider_timestamp=provider_timestamp,
            candles=tuple(completed),
        )
        dataset = OHLCVDataset(
            symbol=mapping.internal,
            timeframe=timeframe,
            source=self.name,
            requested_at=requested_at,
            provider_timestamp=provider_timestamp,
            candles=tuple(completed),
            request_latency_ms=int((time.perf_counter() - started) * 1000),
            freshness_status=FreshnessStatus.UNKNOWN,
            freshness_age_seconds=None,
            completeness_status=dataset_completeness(provisional),
            provider_attempts=(self.name,),
        )
        return validate_ohlcv_dataset(refresh_candle_freshness(dataset))
