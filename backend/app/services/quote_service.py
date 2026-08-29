import asyncio

from app.config import settings
from app.models import Quote, QuoteStatus
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.finnhub import FinnhubProvider
from app.providers.twelve_data import TwelveDataProvider
from app.services.cache import TTLCache
from app.symbols import normalize_symbol


class QuoteService:
    def __init__(self) -> None:
        # The canonical historical/analysis provider remains Twelve Data.
        # Alpha Vantage and Finnhub are quote fallbacks and must not silently
        # replace the canonical OHLCV dataset used by technical analysis.
        self.providers = [TwelveDataProvider(), AlphaVantageProvider(), FinnhubProvider()]
        self.provider = self.providers[0]
        self.cache: TTLCache[Quote] = TTLCache()

    async def get_quote(self, symbol: str, force_refresh: bool = False) -> Quote:
        key = symbol.strip().upper()
        if not force_refresh:
            cached = self.cache.get(key)
            if cached is not None:
                return cached.model_copy(update={"cache_hit": True})

        last_quote: Quote | None = None
        for provider in self.providers:
            quote = await provider.get_quote(key)
            last_quote = quote
            if quote.status == QuoteStatus.LIVE:
                self.cache.set(key, quote.model_copy(update={"cache_hit": False}), settings.quote_cache_seconds)
                return quote.model_copy(update={"cache_hit": False})

        if last_quote is not None:
            return last_quote.model_copy(update={"cache_hit": False})
        mapping = normalize_symbol(key)
        return Quote(
            symbol=mapping.internal,
            provider_symbol=mapping.twelve_data,
            status=QuoteStatus.UNAVAILABLE,
            source="multi_provider",
            error="No configured provider returned a fresh quote.",
            cache_hit=False,
        )

    async def _get_quote_bounded(self, symbol: str, force_refresh: bool) -> Quote:
        try:
            return await asyncio.wait_for(self.get_quote(symbol, force_refresh=force_refresh), timeout=8.0)
        except asyncio.TimeoutError:
            mapping = normalize_symbol(symbol)
            return Quote(
                symbol=mapping.internal,
                provider_symbol=mapping.twelve_data,
                status=QuoteStatus.UNAVAILABLE,
                source="multi_provider",
                error="Market-data providers exceeded the API latency budget.",
                cache_hit=False,
            )

    async def get_quotes(self, symbols: list[str], force_refresh: bool = False) -> list[Quote]:
        return list(await asyncio.gather(*(self._get_quote_bounded(symbol, force_refresh) for symbol in symbols)))

    async def provider_status(self) -> list[dict]:
        results = []
        for provider in self.providers:
            configured = await provider.health()
            results.append(
                {
                    "provider": provider.name,
                    "configured": configured,
                    "reachable": configured,
                    "message": "Configured; live requests are available." if configured else "Not configured.",
                }
            )
        return results
