from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import Quote, QuoteStatus
from app.providers.base import MarketDataProvider
from app.symbols import normalize_symbol


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    base_url = "https://www.alphavantage.co/query"

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if text.isdigit():
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                parsed = datetime.strptime(text, fmt)
                return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)
            except ValueError:
                continue
        return None

    async def get_quote(self, internal_symbol: str) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        if not settings.alpha_vantage_api_key:
            return Quote(symbol=mapping.internal, provider_symbol=mapping.alpha_vantage, source=self.name, status=QuoteStatus.UNAVAILABLE, error="ALPHA_VANTAGE_API_KEY is not configured.")

        started = time.perf_counter()
        params: dict[str, str]
        if mapping.asset_class == "crypto":
            params = {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": mapping.alpha_vantage.split("/")[0], "to_currency": mapping.alpha_vantage.split("/")[1], "apikey": settings.alpha_vantage_api_key}
        elif mapping.asset_class == "forex":
            params = {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": mapping.alpha_vantage[:3], "to_currency": mapping.alpha_vantage[3:], "apikey": settings.alpha_vantage_api_key}
        else:
            params = {"function": "GLOBAL_QUOTE", "symbol": mapping.alpha_vantage, "apikey": settings.alpha_vantage_api_key}

        try:
            timeout = httpx.Timeout(settings.http_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
            if payload.get("Note") or payload.get("Information") or payload.get("Error Message"):
                raise ValueError(str(payload.get("Note") or payload.get("Information") or payload.get("Error Message")))

            if mapping.asset_class in {"crypto", "forex"}:
                block = payload.get("Realtime Currency Exchange Rate", {})
                raw_price = block.get("5. Exchange Rate")
                provider_ts = self._timestamp(block.get("6. Last Refreshed"))
            else:
                block = payload.get("Global Quote", {})
                raw_price = block.get("05. price")
                provider_ts = self._timestamp(block.get("07. latest trading day"))

            if raw_price is None or provider_ts is None:
                raise ValueError("Alpha Vantage response lacks a usable price and authoritative timestamp.")
            price = float(raw_price)
            if price <= 0:
                raise ValueError("Alpha Vantage returned a non-positive price.")
            observed_at = datetime.now(timezone.utc)
            age = (observed_at - provider_ts).total_seconds()
            if age < -60 or age > settings.stale_quote_seconds:
                raise ValueError(f"Alpha Vantage quote is stale or timestamp is invalid: age={age:.2f}s.")
            return Quote(symbol=mapping.internal, provider_symbol=mapping.alpha_vantage, price=price, timestamp=provider_ts, provider_timestamp=provider_ts, observed_at=observed_at, source=self.name, status=QuoteStatus.LIVE, latency_ms=int((time.perf_counter()-started)*1000), cache_hit=False)
        except (httpx.HTTPError, ValueError) as exc:
            return Quote(symbol=mapping.internal, provider_symbol=mapping.alpha_vantage, source=self.name, status=QuoteStatus.UNAVAILABLE, latency_ms=int((time.perf_counter()-started)*1000), error=str(exc), cache_hit=False)

    async def get_candles(self, *args, **kwargs):
        raise RuntimeError("Alpha Vantage candle fallback is disabled for the free-tier project scope.")

    async def health(self) -> bool:
        return bool(settings.alpha_vantage_api_key)
