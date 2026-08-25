import asyncio
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import Quote, QuoteStatus
from app.providers.base import MarketDataProvider
from app.services.technical_analysis import Candle
from app.symbols import normalize_symbol


class TwelveDataProvider(MarketDataProvider):
    name = "twelve_data"
    base_url = "https://api.twelvedata.com"

    async def get_quote(self, internal_symbol: str) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        if not settings.twelve_data_api_key:
            return Quote(symbol=mapping.internal, provider_symbol=mapping.twelve_data, status=QuoteStatus.UNAVAILABLE, source=self.name, error="TWELVE_DATA_API_KEY is not configured.")
        started = time.perf_counter()
        params = {"symbol": mapping.twelve_data, "apikey": settings.twelve_data_api_key}
        last_error = "Unknown provider error"
        for attempt in range(settings.http_max_retries + 1):
            try:
                timeout = httpx.Timeout(settings.http_timeout_seconds)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(f"{self.base_url}/price", params=params)
                response.raise_for_status()
                payload = response.json()
                if "code" in payload or "message" in payload and "price" not in payload:
                    last_error = str(payload.get("message", "Provider returned an error"))
                    if attempt < settings.http_max_retries:
                        await asyncio.sleep(2**attempt)
                        continue
                    break
                raw_price = payload.get("price")
                if raw_price is None:
                    last_error = "Provider response did not contain price."
                    if attempt < settings.http_max_retries:
                        await asyncio.sleep(2**attempt)
                        continue
                    break
                price = float(raw_price)
                if price <= 0:
                    last_error = "Provider returned a non-positive price."
                    break
                return Quote(symbol=mapping.internal, provider_symbol=mapping.twelve_data, price=price, timestamp=datetime.now(timezone.utc), source=self.name, status=QuoteStatus.LIVE, latency_ms=int((time.perf_counter() - started) * 1000))
            except (httpx.HTTPError, ValueError) as exc:
                last_error = str(exc)
                if attempt < settings.http_max_retries:
                    await asyncio.sleep(2**attempt)
        return Quote(symbol=mapping.internal, provider_symbol=mapping.twelve_data, status=QuoteStatus.UNAVAILABLE, source=self.name, latency_ms=int((time.perf_counter() - started) * 1000), error=last_error)

    async def get_candles(self, internal_symbol: str, interval: str, outputsize: int = 250) -> list[Candle]:
        mapping = normalize_symbol(internal_symbol)
        if not settings.twelve_data_api_key:
            raise RuntimeError("TWELVE_DATA_API_KEY is not configured.")
        params = {"symbol": mapping.twelve_data, "interval": interval, "outputsize": str(min(max(outputsize, 50), 5000)), "apikey": settings.twelve_data_api_key}
        timeout = httpx.Timeout(settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{self.base_url}/time_series", params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error" or "values" not in payload:
            raise ValueError(str(payload.get("message", "Provider returned no historical data.")))
        candles: list[Candle] = []
        # Twelve Data returns time-series values ordered newest-first by default.
        for row in reversed(payload["values"]):
            try:
                candles.append(Candle(timestamp=str(row["datetime"]), open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]), volume=float(row["volume"]) if row.get("volume") is not None else None))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Provider returned malformed candle data.") from exc
        return candles

    async def health(self) -> bool:
        return bool(settings.twelve_data_api_key)
