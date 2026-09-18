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

    Public requests are serialized and rate-limited because the provider is
    used as a production fallback and research may request multiple timeframes.
    Incomplete candles are removed before analytical datasets are returned.
    """

    name = "kraken_public"
    base_url = "https://api.kraken.com/0/public"
    REQUEST_INTERVAL_SECONDS = 1.05
    MAX_RETRIES = 2
    CANDLE_CACHE_SECONDS = 90.0
    _candle_cache: dict[tuple[str, str, int, str | None, str | None], tuple[float, OHLCVDataset]] = {}
    CANDLE_CACHE_SECONDS = 90.0
    _candle_cache: dict[tuple[str, str, int, str | None, str | None], tuple[float, OHLCVDataset]] = {}

    _intervals = {
        Timeframe.MINUTE_15: 15,
        Timeframe.HOUR_1: 60,
        Timeframe.HOUR_4: 240,
        Timeframe.DAY_1: 1440,
    }

    _pairs = {
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

    def __init__(self) -> None:
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

    @property
    def configured(self) -> bool:
        return True

    @property
    def supports_batch_quotes(self) -> bool:
        return True

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

    @staticmethod
    def _find_ticker_row(result: dict, pair: str) -> dict | None:
        if isinstance(result.get(pair), dict):
            return result[pair]
        upper_pair = pair.upper()
        for key, value in result.items():
            if key.upper() == upper_pair and isinstance(value, dict):
                return value
        # Kraken may return a canonical REST key such as XXBTZUSD for XBTUSD.
        normalized = upper_pair.replace("XBT", "BTC", 1)
        for key, value in result.items():
            key_normalized = key.upper().replace("XBT", "BTC", 1).replace("Z", "", 1)
            if key_normalized == normalized and isinstance(value, dict):
                return value
        return None

    @classmethod
    def _quote_from_row(
        cls,
        internal_symbol: str,
        pair: str,
        row: dict,
        latency_ms: int,
    ) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        close = row.get("c")
        if not isinstance(close, list) or not close:
            raise ValueError(f"Kraken returned no last-trade price for {pair}.")
        price = float(close[0])
        if price <= 0:
            raise ValueError(f"Kraken returned a non-positive price for {pair}.")
        observed_at = datetime.now(timezone.utc)
        return Quote(
            symbol=mapping.internal,
            provider_symbol=pair,
            price=price,
            timestamp=observed_at,
            provider_timestamp=observed_at,
            observed_at=observed_at,
            source=cls.name,
            status=QuoteStatus.LIVE,
            latency_ms=latency_ms,
            freshness_status=FreshnessStatus.FRESH,
            freshness_age_seconds=0.0,
            completeness_status=CompletenessStatus.COMPLETE,
            provider_attempts=(cls.name,),
        )

    async def get_quotes(self, internal_symbols: list[str]) -> list[Quote]:
        if not internal_symbols:
            return []
        mappings = [normalize_symbol(symbol) for symbol in internal_symbols]
        pairs = [self._provider_pair(mapping.internal) for mapping in mappings]
        started = time.perf_counter()
        payload = await self._request_json(
            "Ticker",
            {"pair": ",".join(pairs)},
            timeout_seconds=8.0,
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Kraken returned no ticker result.")
        latency_ms = int((time.perf_counter() - started) * 1000)
        quotes: list[Quote] = []
        for mapping, pair in zip(mappings, pairs):
            row = self._find_ticker_row(result, pair)
            if row is None:
                raise ValueError(f"Kraken returned no ticker data for {pair}.")
            quotes.append(self._quote_from_row(mapping.internal, pair, row, latency_ms))
        return quotes

    async def get_quote(self, internal_symbol: str) -> Quote:
        return (await self.get_quotes([internal_symbol]))[0]

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
        cache_key = (
            mapping.internal,
            timeframe.value,
            min(max(outputsize, 30), 720),
            start_date.astimezone(timezone.utc).isoformat() if start_date else None,
            end_date.astimezone(timezone.utc).isoformat() if end_date else None,
        )
        cached = self._candle_cache.get(cache_key)
        now_monotonic = time.monotonic()
        if cached is not None and now_monotonic - cached[0] < self.CANDLE_CACHE_SECONDS:
            cached_dataset = refresh_candle_freshness(cached[1])
            if cached_dataset.freshness_status in {FreshnessStatus.FRESH, FreshnessStatus.DELAYED}:
                return cached_dataset.model_copy(update={"cache_hit": True, "request_latency_ms": 0})
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
        validated = validate_ohlcv_dataset(refresh_candle_freshness(dataset))
        self._candle_cache[cache_key] = (time.monotonic(), validated)
        return validated
