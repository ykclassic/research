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


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"
    base_url = "https://finnhub.io/api/v1"

    _resolutions = {
        Timeframe.MINUTE_5: "5",
        Timeframe.MINUTE_15: "15",
        Timeframe.MINUTE_30: "30",
        Timeframe.HOUR_1: "60",
        Timeframe.HOUR_4: "240",
        Timeframe.DAY_1: "D",
    }

    @property
    def configured(self) -> bool:
        return bool(settings.finnhub_api_key.strip())

    @staticmethod
    def _provider_symbol(internal_symbol: str) -> str:
        mapping = normalize_symbol(internal_symbol)
        if mapping.asset_class in {"stock", "etf"}:
            return mapping.twelve_data
        if mapping.asset_class == "crypto":
            base, quote = mapping.internal.split("/")
            return f"BINANCE:{base}{quote}"
        base, quote = mapping.internal.split("/")
        return f"OANDA:{base}_{quote}"

    @staticmethod
    def _timestamp(value: int | float | str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    async def _get(self, path: str, params: dict[str, str]) -> dict:
        if not self.configured:
            raise RuntimeError("FINNHUB_API_KEY is not configured.")
        query = dict(params)
        query["token"] = settings.finnhub_api_key
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.provider_timeout_seconds)
        ) as client:
            response = await client.get(f"{self.base_url}/{path}", params=query)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise ValueError(str(payload["error"]))
        return payload

    async def get_quote(self, internal_symbol: str) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        started = time.perf_counter()
        provider_symbol = self._provider_symbol(internal_symbol)
        try:
            payload = await self._get("quote", {"symbol": provider_symbol})
            price = float(payload.get("c") or 0)
            provider_timestamp = self._timestamp(payload.get("t"))
            if price <= 0 or provider_timestamp is None:
                raise ValueError("Finnhub returned an incomplete quote.")
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
                provider_symbol=provider_symbol,
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
                provider_symbol=provider_symbol,
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
        provider_symbol = self._provider_symbol(internal_symbol)
        now = datetime.now(timezone.utc)
        start = int((start_date or (now.timestamp() - timeframe.seconds * outputsize)))
        end = int((end_date or now).timestamp())
        payload = await self._get(
            {
                "stock": "stock/candle",
                "etf": "stock/candle",
                "forex": "forex/candle",
                "crypto": "crypto/candle",
            }[mapping.asset_class],
            {"symbol": provider_symbol, "resolution": self._resolutions[timeframe], "from": str(start), "to": str(end)},
        )
        if payload.get("s") != "ok":
            raise ValueError(f"Finnhub candle response status: {payload.get('s')}")
        rows = zip(payload.get("t", []), payload.get("o", []), payload.get("h", []), payload.get("l", []), payload.get("c", []), payload.get("v", []))
        candles: list[Candle] = []
        duration = timeframe.seconds
        for timestamp, open_, high, low, close, volume in rows:
            candle_time = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            candles.append(
                Candle(
                    timestamp=candle_time,
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume) if volume is not None else None,
                    symbol=mapping.internal,
                    timeframe=timeframe,
                    source=self.name,
                    is_complete=candle_time.timestamp() + duration <= now.timestamp(),
                )
            )
        if not candles:
            raise ValueError("Finnhub returned no candles.")
        candles.sort(key=lambda item: item.timestamp)
        requested_at = now
        provider_timestamp = candles[-1].timestamp
        age = max(0.0, (now - provider_timestamp).total_seconds())
        freshness = freshness_for_age(age, timeframe.seconds + settings.stale_quote_seconds)
        provisional = OHLCVDataset.model_construct(
            symbol=mapping.internal,
            timeframe=timeframe,
            source=self.name,
            requested_at=requested_at,
            provider_timestamp=provider_timestamp,
            candles=tuple(candles),
        )
        return validate_ohlcv_dataset(
            OHLCVDataset(
                symbol=mapping.internal,
                timeframe=timeframe,
                source=self.name,
                requested_at=requested_at,
                provider_timestamp=provider_timestamp,
                candles=tuple(candles),
                request_latency_ms=0,
                freshness_status=freshness,
                freshness_age_seconds=age,
                completeness_status=dataset_completeness(provisional),
                provider_attempts=(self.name,),
            )
        )
