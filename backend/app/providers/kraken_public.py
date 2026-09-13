from __future__ import annotations

import asyncio
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

    Kraken currently recommends keeping public REST market-data calls at one
    request per second or slower. The provider therefore serializes all public
    requests made by this instance and enforces a small safety margin. This is
    important because research reports request four OHLC timeframes for the same
    asset concurrently.
    """

    name = "kraken_public"
    base_url = "https://api.kraken.com/0/public"
    REQUEST_INTERVAL_SECONDS = 1.05
    MAX_RETRIES = 2

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

    def __init__(self) -> None:
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

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

    @staticmethod
    def _is_rate_limit_error(errors: object) -> bool:
        if not isinstance(errors, list):
            return False
        return any("rate limit" in str(error).lower() for error in errors)

    @staticmethod
    def _retry_after_seconds(response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(1.0, min(float(header), 10.0))
            except ValueError:
                pass
        return min(2.0 * (attempt + 1), 5.0)

    async def _request_json(self, endpoint: str, params: dict[str, str], timeout_seconds: float) -> dict:
        async with self._request_lock:
            for attempt in range(self.MAX_RETRIES + 1):
                wait = self.REQUEST_INTERVAL_SECONDS - (time.monotonic() - self._last_request_at)
                if wait > 0:
                    await asyncio.sleep(wait)

                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
                        response = await client.get(f"{self.base_url}/{endpoint}", params=params)
                    self._last_request_at = time.monotonic()

                    if response.status_code == 429:
                        if attempt < self.MAX_RETRIES:
                            await asyncio.sleep(self._retry_after_seconds(response, attempt))
                            continue
                        response.raise_for_status()

                    if response.status_code >= 500 and attempt < self.MAX_RETRIES:
                        await asyncio.sleep(min(2.0 * (attempt + 1), 5.0))
                        continue

                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("Kraken returned an invalid JSON payload.")

                    errors = payload.get("error")
                    if errors:
                        if self._is_rate_limit_error(errors) and attempt < self.MAX_RETRIES:
                            await asyncio.sleep(min(2.0 * (attempt + 1), 5.0))
                            continue
                        raise ValueError(f"Kraken API error: {errors}")
                    return payload
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt >= self.MAX_RETRIES:
                        raise
                    await asyncio.sleep(min(2.0 * (attempt + 1), 5.0))
                except httpx.HTTPStatusError:
                    raise

        raise RuntimeError("Kraken request failed after all retry attempts.")

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
        payload = await self._request_json("Ticker", {"pair": pair}, timeout_seconds=8.0)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Kraken returned no ticker result.")
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

        payload = await self._request_json("OHLC", params, timeout_seconds=10.0)
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
