from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider, dataset_completeness, freshness_for_age
from app.services.data_validation import validate_ohlcv_dataset
from app.symbols import normalize_symbol


class TwelveDataProvider(MarketDataProvider):
    name = "twelve_data"
    base_url = "https://api.twelvedata.com"

    _intervals = {
        Timeframe.MINUTE_5: "5min",
        Timeframe.MINUTE_15: "15min",
        Timeframe.MINUTE_30: "30min",
        Timeframe.HOUR_1: "1h",
        Timeframe.HOUR_4: "4h",
        Timeframe.DAY_1: "1day",
    }

    @property
    def configured(self) -> bool:
        return bool(settings.twelve_data_api_key.strip())

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Provider returned invalid candle timestamp: {value}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _parse_provider_quote_timestamp(cls, payload: dict) -> datetime | None:
        value = payload.get("last_update_at")
        if value is None:
            value = payload.get("timestamp")
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        text = str(value).strip()
        try:
            if text.isdigit():
                return datetime.fromtimestamp(float(text), tz=timezone.utc)
            return cls._parse_timestamp(text)
        except ValueError as exc:
            raise ValueError(f"Provider returned invalid quote timestamp: {value}") from exc

    @staticmethod
    def _format_range_timestamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async def get_quote(self, internal_symbol: str) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        if not self.configured:
            return Quote(
                symbol=mapping.internal,
                provider_symbol=mapping.twelve_data,
                status=QuoteStatus.UNAVAILABLE,
                source=self.name,
                error="TWELVE_DATA_API_KEY is not configured.",
            )

        started = time.perf_counter()
        params = {
            "symbol": mapping.twelve_data,
            "interval": "1min",
            "apikey": settings.twelve_data_api_key,
        }
        last_error = "Unknown provider error"
        for attempt in range(settings.http_max_retries + 1):
            try:
                request_started = time.perf_counter()
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.provider_timeout_seconds)
                ) as client:
                    response = await client.get(f"{self.base_url}/quote", params=params)
                latency_ms = int((time.perf_counter() - request_started) * 1000)
                response.raise_for_status()
                payload = response.json()
                if "code" in payload or ("message" in payload and "close" not in payload):
                    raise ValueError(str(payload.get("message", "Provider returned an error")))

                raw_price = payload.get("close", payload.get("price"))
                if raw_price is None:
                    raise ValueError("Provider response did not contain a current quote price.")
                price = float(raw_price)
                if price <= 0:
                    raise ValueError("Provider returned a non-positive price.")

                observed_at = datetime.now(timezone.utc)
                provider_timestamp = self._parse_provider_quote_timestamp(payload) or observed_at
                age = max(0.0, (observed_at - provider_timestamp).total_seconds())
                freshness = freshness_for_age(age, settings.stale_quote_seconds)
                status = {
                    FreshnessStatus.FRESH: QuoteStatus.LIVE,
                    FreshnessStatus.DELAYED: QuoteStatus.DELAYED,
                    FreshnessStatus.STALE: QuoteStatus.STALE,
                }.get(freshness, QuoteStatus.UNAVAILABLE)
                return Quote(
                    symbol=mapping.internal,
                    provider_symbol=mapping.twelve_data,
                    price=price,
                    timestamp=provider_timestamp,
                    provider_timestamp=provider_timestamp,
                    observed_at=observed_at,
                    source=self.name,
                    status=status,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    cache_hit=False,
                    freshness_status=freshness,
                    freshness_age_seconds=age,
                    completeness_status=CompletenessStatus.COMPLETE,
                    provider_attempts=(self.name,),
                )
            except (httpx.HTTPError, ValueError) as exc:
                last_error = str(exc)
                if attempt < settings.http_max_retries:
                    await asyncio.sleep(2**attempt)
        return Quote(
            symbol=mapping.internal,
            provider_symbol=mapping.twelve_data,
            status=QuoteStatus.UNAVAILABLE,
            source=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=last_error,
            cache_hit=False,
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
        if (start_date is None) != (end_date is None):
            raise ValueError("Historical candle ranges require both start_date and end_date.")
        if start_date is not None and end_date is not None and start_date >= end_date:
            raise ValueError("Historical candle start_date must be before end_date.")
        timeframe = Timeframe(timeframe)
        mapping = normalize_symbol(internal_symbol)
        if not self.configured:
            raise RuntimeError("TWELVE_DATA_API_KEY is not configured.")

        interval = self._intervals[timeframe]
        requested_at = datetime.now(timezone.utc)
        params = {
            "symbol": mapping.twelve_data,
            "interval": interval,
            "apikey": settings.twelve_data_api_key,
        }
        if start_date is not None and end_date is not None:
            params["start_date"] = self._format_range_timestamp(start_date)
            params["end_date"] = self._format_range_timestamp(end_date)
        else:
            params["outputsize"] = str(min(max(outputsize, 50), 5000))

        last_error = "Unknown provider error"
        started = time.perf_counter()
        for attempt in range(settings.http_max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.provider_timeout_seconds)
                ) as client:
                    response = await client.get(f"{self.base_url}/time_series", params=params)
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") == "error" or "values" not in payload:
                    raise ValueError(str(payload.get("message", "Provider returned no historical data.")))

                candles: list[Candle] = []
                now = datetime.now(timezone.utc)
                duration = timedelta(seconds=timeframe.seconds)
                for row in reversed(payload["values"]):
                    timestamp = self._parse_timestamp(str(row["datetime"]))
                    candles.append(
                        Candle(
                            timestamp=timestamp,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]) if row.get("volume") is not None else None,
                            symbol=mapping.internal,
                            timeframe=timeframe,
                            source=self.name,
                            is_complete=timestamp + duration <= now,
                        )
                    )
                if not candles:
                    raise ValueError("Provider returned no historical candles.")

                provider_timestamp = candles[-1].timestamp
                age = max(0.0, (now - provider_timestamp).total_seconds())
                freshness = freshness_for_age(age, timeframe.seconds + settings.stale_quote_seconds)
                dataset = OHLCVDataset(
                    symbol=mapping.internal,
                    timeframe=timeframe,
                    source=self.name,
                    requested_at=requested_at,
                    provider_timestamp=provider_timestamp,
                    candles=tuple(candles),
                    request_latency_ms=int((time.perf_counter() - started) * 1000),
                    freshness_status=freshness,
                    freshness_age_seconds=age,
                    completeness_status=dataset_completeness(
                        OHLCVDataset.model_construct(
                            symbol=mapping.internal,
                            timeframe=timeframe,
                            source=self.name,
                            requested_at=requested_at,
                            provider_timestamp=provider_timestamp,
                            candles=tuple(candles),
                        )
                    ),
                    provider_attempts=(self.name,),
                )
                return validate_ohlcv_dataset(dataset)
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                last_error = str(exc)
                if attempt < settings.http_max_retries:
                    await asyncio.sleep(2**attempt)
        raise ValueError(last_error)
