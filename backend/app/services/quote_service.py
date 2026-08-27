import asyncio

from app.config import settings
from app.models import Quote, QuoteStatus
from app.providers.twelve_data import TwelveDataProvider
from app.services.cache import TTLCache
from app.symbols import normalize_symbol


class QuoteService:
    def __init__(self) -> None:
        self.provider = TwelveDataProvider()
        self.cache: TTLCache[Quote] = TTLCache()

    async def get_quote(self, symbol: str, force_refresh: bool = False) -> Quote:
        key = symbol.strip().upper()
        if not force_refresh:
            cached = self.cache.get(key)
            if cached is not None:
                return cached.model_copy(update={"cache_hit": True})

        quote = await self.provider.get_quote(key)
        if quote.status == QuoteStatus.LIVE:
            self.cache.set(key, quote.model_copy(update={"cache_hit": False}), settings.quote_cache_seconds)
        return quote.model_copy(update={"cache_hit": False})

    async def _get_quote_bounded(self, symbol: str, force_refresh: bool) -> Quote:
        """Return a deterministic unavailable result instead of blocking the API indefinitely."""
        try:
            # Keep the aggregate /quotes endpoint below the frontend's 12s request budget.
            return await asyncio.wait_for(
                self.get_quote(symbol, force_refresh=force_refresh),
                timeout=8.0,
            )
        except asyncio.TimeoutError:
            mapping = normalize_symbol(symbol)
            return Quote(
                symbol=mapping.internal,
                provider_symbol=mapping.twelve_data,
                status=QuoteStatus.UNAVAILABLE,
                source=self.provider.name,
                error="Market-data provider exceeded the API latency budget.",
                cache_hit=False,
            )

    async def get_quotes(self, symbols: list[str], force_refresh: bool = False) -> list[Quote]:
        """Fetch independent symbols concurrently and preserve request order."""
        return list(await asyncio.gather(
            *(self._get_quote_bounded(symbol, force_refresh) for symbol in symbols)
        ))
