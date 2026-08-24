import asyncio

from app.config import settings
from app.models import Quote, QuoteStatus
from app.providers.twelve_data import TwelveDataProvider
from app.services.cache import TTLCache


class QuoteService:
    def __init__(self) -> None:
        self.provider = TwelveDataProvider()
        self.cache: TTLCache[Quote] = TTLCache()

    async def get_quote(self, symbol: str, force_refresh: bool = False) -> Quote:
        key = symbol.strip().upper()
        if not force_refresh:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        quote = await self.provider.get_quote(key)
        if quote.status == QuoteStatus.LIVE:
            self.cache.set(key, quote, settings.quote_cache_seconds)
        return quote

    async def get_quotes(self, symbols: list[str], force_refresh: bool = False) -> list[Quote]:
        """Fetch independent symbols concurrently while preserving request order."""
        return list(await asyncio.gather(
            *(self.get_quote(symbol, force_refresh=force_refresh) for symbol in symbols)
        ))
