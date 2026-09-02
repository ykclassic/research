from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider, dataset_completeness, freshness_for_age
from app.services.data_validation import validate_ohlcv_dataset
from app.symbols import normalize_symbol


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    base_url = "https://www.alphavantage.co/query"

    _intervals = {
        Timeframe.MINUTE_5: "5min",
        Timeframe.MINUTE_15: "15min",
        Timeframe.MINUTE_30: "30min",
        Timeframe.HOUR_1: "60min",
        Timeframe.HOUR_4: "60min",
        Timeframe.DAY_1: "daily",
    }

    @property
    def configured(self) -> bool:
        return bool(settings.alpha_vantage_api_key.strip())

    @staticmethod
    def _timestamp(value: str | int | float | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _split_pair(symbol: str) -> tuple[str, str]:
        base, quote = normalize_symbol(symbol).internal.split("/")
        return base, quote

    async def _get(self, params: dict[str, str]) -> dict:
        if not self.configured:
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured.")
        query = dict(params)
        query["apikey"] = settings.alpha_vantage_api_key
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.provider_timeout_seconds)
        ) as client:
            response = await client.get(self.base_url, params=query)
        response.raise_for_status()
        payload = response.json()
        if "Error Message" in payload:
            raise ValueError(str(payload["Error Message"]))
        if "Note" in payload:
            raise ValueError(str(payload["Note"]))
        return payload

    async def get_quote(self, internal_symbol: str) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        started = time.perf_counter()
        try:
            if mapping.asset_class in {"stock", "etf"}:
                payload = await self._get({"function": "GLOBAL_QUOTE", "symbol": mapping.twelve_data})
                row = payload.get("Global Quote", {})
                price = float(row.get("05. price", 0))
                provider_timestamp = self._timestamp(row.get("07. latest trading day"))
                if provider_timestamp is not None:
                    provider_timestamp = provider_timestamp.replace(hour=23, minute=59, second=59)
            else:
                base, quote = self._split_pair(internal_symbol)
                payload = await self._get(
                    {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": base, "to_currency": quote}
                )
                row = payload.get("Realtime Currency Exchange Rate", {})
                price = float(row.get("5. Exchange Rate", 0))
                provider_timestamp = self._timestamp(row.get("6. Last Refreshed"))
            if price <= 0 or provider_timestamp is None:
                raise ValueError("Alpha Vantage returned an incomplete quote.")
            observed_at = datetime.now(timezone.utc)
            age = max(0.0, (observed_at - provider_timestamp).total_seconds())
            freshness = freshness_for_age(age, settings.stale_quote_seconds)
            status = {
                FreshnessStatus.FRESH: QuoteStatus.LIVE,
                FreshnessStatus.DELAYED: QuoteStatus.DELAYED,
                FreshnessStatus.STALE: QuoteStatus.STALE,
            }[freshness]
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
                freshness_status=freshness,
                freshness_age_seconds=age,
                completeness_status=CompletenessStatus.COMPLETE,
                provider_attempts=(self.name,),
            )
        except (httpx.HTTPError, ValueError, RuntimeError, TypeError) as exc:
            return Quote(
                symbol=mapping.internal,
                provider_symbol=mapping.twelve_data,
                status=QuoteStatus.UNAVAILABLE,
                source=self.name,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
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
        timeframe = Timeframe(timeframe)
        started = time.perf_counter()
        now = datetime.now(timezone.utc)
        if start_date is not None or end_date is not None:
            raise ValueError("Alpha Vantage fallback currently supports rolling windows only.")

        if mapping.asset_class in {"stock", "etf"}:
            if timeframe == Timeframe.DAY_1:
                params = {"function": "TIME_SERIES_DAILY", "symbol": mapping.twelve_data, "outputsize": "full"}
                series_name = "Time Series (Daily)"
                timestamp_parser = lambda value: datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            else:
                params = {
                    "function": "TIME_SERIES_INTRADAY",
                    "symbol": mapping.twelve_data,
                    "interval": self._intervals[timeframe],
                    "outputsize": "full",
                }
                series_name = f"Time Series ({self._intervals[timeframe]})"
                timestamp_parser = self._timestamp
        elif mapping.asset_class == "forex":
            base, quote = self._split_pair(internal_symbol)
            if timeframe == Timeframe.DAY_1:
                params = {"function": "FX_DAILY", "from_symbol": base, "to_symbol": quote, "outputsize": "full"}
                series_name = "Time Series FX (Daily)"
            else:
                params = {
                    "function": "FX_INTRADAY",
                    "from_symbol": base,
                    "to_symbol": quote,
                    "interval": self._intervals[timeframe],
                    "outputsize": "full",
                }
                series_name = f"Time Series FX ({self._intervals[timeframe]})"
            timestamp_parser = self._timestamp
        else:
            base, quote = self._split_pair(internal_symbol)
            if timeframe == Timeframe.DAY_1:
                params = {"function": "DIGITAL_CURRENCY_DAILY", "symbol": base, "market": quote}
                series_name = "Time Series (Digital Currency Daily)"
            else:
                params = {
                    "function": "CRYPTO_INTRADAY",
                    "symbol": base,
                    "market": quote,
                    "interval": self._intervals[timeframe],
                    "outputsize": "full",
                }
                series_name = f"Time Series Crypto ({self._intervals[timeframe]})"
            timestamp_parser = self._timestamp

        payload = await self._get(params)
        series = payload.get(series_name)
        if not isinstance(series, dict):
            raise ValueError(f"Alpha Vantage returned no series for {internal_symbol} {timeframe.value}.")

        candles: list[Candle] = []
        duration = timeframe.seconds
        for raw_timestamp, row in series.items():
            timestamp = timestamp_parser(raw_timestamp)
            if timestamp is None:
                continue
            close_key = "4. close"
            open_key = "1. open"
            high_key = "2. high"
            low_key = "3. low"
            volume_key = "5. volume"
            candles.append(
                Candle(
                    timestamp=timestamp,
                    open=float(row[open_key]),
                    high=float(row[high_key]),
                    low=float(row[low_key]),
                    close=float(row[close_key]),
                    volume=float(row[volume_key]) if row.get(volume_key) is not None else None,
                    symbol=mapping.internal,
                    timeframe=timeframe,
                    source=self.name,
                    is_complete=timestamp.timestamp() + duration <= now.timestamp(),
                )
            )
        candles.sort(key=lambda item: item.timestamp)
        if not candles:
            raise ValueError("Alpha Vantage returned no candles.")
        candles = candles[-min(max(outputsize, 50), len(candles)):]
        provider_timestamp = candles[-1].timestamp
        age = max(0.0, (now - provider_timestamp).total_seconds())
        freshness = freshness_for_age(age, timeframe.seconds + settings.stale_quote_seconds)
        provisional = OHLCVDataset.model_construct(
            symbol=mapping.internal,
            timeframe=timeframe,
            source=self.name,
            requested_at=now,
            provider_timestamp=provider_timestamp,
            candles=tuple(candles),
        )
        return validate_ohlcv_dataset(
            OHLCVDataset(
                symbol=mapping.internal,
                timeframe=timeframe,
                source=self.name,
                requested_at=now,
                provider_timestamp=provider_timestamp,
                candles=tuple(candles),
                request_latency_ms=int((time.perf_counter() - started) * 1000),
                freshness_status=freshness,
                freshness_age_seconds=age,
                completeness_status=dataset_completeness(provisional),
                provider_attempts=(self.name,),
            )
        )
