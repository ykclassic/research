from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider, ProviderUsage, dataset_completeness, freshness_for_age
from app.providers.errors import ProviderErrorCode, classify_provider_error, error_label, retryable_provider_error
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

    def __init__(self) -> None:
        self._last_usage: ProviderUsage | None = None

    @property
    def configured(self) -> bool:
        return bool(settings.twelve_data_api_key.strip())

    @property
    def supports_batch_quotes(self) -> bool:
        return True

    @property
    def usage(self) -> ProviderUsage | None:
        return self._last_usage

    def _record_usage(self, headers: httpx.Headers) -> None:
        used = headers.get("api-credits-used")
        remaining = headers.get("api-credits-left")
        if used is None and remaining is None:
            return
        try:
            used_value = int(used) if used is not None else None
        except ValueError:
            used_value = None
        try:
            remaining_value = int(remaining) if remaining is not None else None
        except ValueError:
            remaining_value = None
        self._last_usage = ProviderUsage(
            credits_used=used_value,
            credits_remaining=remaining_value,
            observed_at=datetime.now(timezone.utc),
        )

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
        value = payload.get("last_quote_at")
        if value is None:
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

    @classmethod
    def _quote_from_payload(cls, internal_symbol: str, payload: dict, *, latency_ms: int) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        if payload.get("status") == "error" or "code" in payload:
            message = str(payload.get("message", "Provider returned an error"))
            code = classify_provider_error(message=message, status_code=int(payload["code"]) if str(payload.get("code", "")).isdigit() else None)
            return Quote(
                symbol=mapping.internal,
                provider_symbol=mapping.twelve_data,
                status=QuoteStatus.UNAVAILABLE,
                source=cls.name,
                latency_ms=latency_ms,
                error=f"{error_label(code)}: {message}",
                error_code=code,
                provider_attempts=(cls.name,),
            )

        raw_price = payload.get("close", payload.get("price"))
        if raw_price is None:
            raise ValueError("Provider response did not contain a current quote price.")
        price = float(raw_price)
        if price <= 0:
            raise ValueError("Provider returned a non-positive price.")

        observed_at = datetime.now(timezone.utc)
        provider_timestamp = cls._parse_provider_quote_timestamp(payload) or observed_at
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
            source=cls.name,
            status=status,
            latency_ms=latency_ms,
            cache_hit=False,
            freshness_status=freshness,
            freshness_age_seconds=age,
            completeness_status=CompletenessStatus.COMPLETE,
            provider_attempts=(cls.name,),
        )

    async def get_quotes(self, internal_symbols: list[str]) -> list[Quote]:
        if not internal_symbols:
            return []
        mappings = [normalize_symbol(symbol) for symbol in internal_symbols]
        if not self.configured:
            return [Quote(
                symbol=mapping.internal,
                provider_symbol=mapping.twelve_data,
                status=QuoteStatus.UNAVAILABLE,
                source=self.name,
                error="Authentication failure: TWELVE_DATA_API_KEY is not configured.",
                error_code=ProviderErrorCode.AUTHENTICATION_FAILURE,
                provider_attempts=(self.name,),
            ) for mapping in mappings]

        started = time.perf_counter()
        provider_symbols = [mapping.twelve_data for mapping in mappings]
        params = {
            "symbol": ",".join(provider_symbols),
            "interval": "1min",
            "apikey": settings.twelve_data_api_key,
        }
        last_error: BaseException | None = None
        last_message = "Unknown provider error"
        for attempt in range(settings.http_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(settings.provider_timeout_seconds)) as client:
                    response = await client.get(f"{self.base_url}/quote", params=params)
                self._record_usage(response.headers)
                latency_ms = int((time.perf_counter() - started) * 1000)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Twelve Data returned an invalid batch quote payload.")
                if payload.get("status") == "error" or "code" in payload:
                    message = str(payload.get("message", "Provider returned an error"))
                    status_code = int(payload["code"]) if str(payload.get("code", "")).isdigit() else None
                    code = classify_provider_error(message=message, status_code=status_code)
                    last_error = ValueError(message)
                    last_message = message
                    if not retryable_provider_error(code):
                        return [Quote(
                            symbol=mapping.internal,
                            provider_symbol=mapping.twelve_data,
                            status=QuoteStatus.UNAVAILABLE,
                            source=self.name,
                            latency_ms=latency_ms,
                            error=f"{error_label(code)}: {message}",
                            error_code=code,
                            provider_attempts=(self.name,),
                            provider_credits_used=self._last_usage.credits_used if self._last_usage else None,
                            provider_credits_remaining=self._last_usage.credits_remaining if self._last_usage else None,
                        ) for mapping in mappings]
                    if attempt < settings.http_max_retries:
                        await asyncio.sleep(2**attempt)
                        continue
                    break

                by_provider_symbol = {
                    str(key): value for key, value in payload.items()
                    if isinstance(value, dict)
                }
                # A single-symbol response is not keyed by symbol; normalize it for completeness.
                if len(mappings) == 1 and payload.get("symbol"):
                    by_provider_symbol[str(payload["symbol"])] = payload

                results: list[Quote] = []
                for mapping in mappings:
                    row = by_provider_symbol.get(mapping.twelve_data)
                    if row is None:
                        # Some APIs normalize case; tolerate that without weakening identity checks.
                        row = next((value for key, value in by_provider_symbol.items() if key.upper() == mapping.twelve_data.upper()), None)
                    if row is None:
                        code = ProviderErrorCode.SYMBOL_UNSUPPORTED
                        results.append(Quote(
                            symbol=mapping.internal,
                            provider_symbol=mapping.twelve_data,
                            status=QuoteStatus.UNAVAILABLE,
                            source=self.name,
                            latency_ms=latency_ms,
                            error=f"{error_label(code)}: Twelve Data did not return this symbol in the batch response.",
                            error_code=code,
                            provider_attempts=(self.name,),
                            provider_credits_used=self._last_usage.credits_used if self._last_usage else None,
                            provider_credits_remaining=self._last_usage.credits_remaining if self._last_usage else None,
                        ))
                        continue
                    results.append(self._quote_from_payload(mapping.internal, row, latency_ms=latency_ms).model_copy(update={
                        "provider_credits_used": self._last_usage.credits_used if self._last_usage else None,
                        "provider_credits_remaining": self._last_usage.credits_remaining if self._last_usage else None,
                    }))
                return results
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                code = classify_provider_error(exc, message=str(exc))
                last_error = exc
                last_message = str(exc)
                if not retryable_provider_error(code) or attempt >= settings.http_max_retries:
                    break
                await asyncio.sleep(2**attempt)

        code = classify_provider_error(last_error, message=last_message)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return [Quote(
            symbol=mapping.internal,
            provider_symbol=mapping.twelve_data,
            status=QuoteStatus.UNAVAILABLE,
            source=self.name,
            latency_ms=latency_ms,
            error=f"{error_label(code)}: {last_message}",
            error_code=code,
            cache_hit=False,
            provider_attempts=(self.name,),
            provider_credits_used=self._last_usage.credits_used if self._last_usage else None,
            provider_credits_remaining=self._last_usage.credits_remaining if self._last_usage else None,
        ) for mapping in mappings]

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
                self._record_usage(response.headers)
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") == "error" or "values" not in payload:
                    message = str(payload.get("message", "Provider returned no historical data."))
                    code = classify_provider_error(message=message, status_code=int(payload["code"]) if str(payload.get("code", "")).isdigit() else None)
                    raise ValueError(f"{error_label(code)}: {message}")

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
                code = classify_provider_error(exc, message=str(exc))
                if not retryable_provider_error(code) or attempt >= settings.http_max_retries:
                    break
                await asyncio.sleep(2**attempt)
        raise ValueError(last_error)
