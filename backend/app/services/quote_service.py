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

        # Never convert unavailable data into a fake/current-looking price.
        if quote.status == QuoteStatus.LIVE:
            self.cache.set(key, quote, settings.quote_cache_seconds)

        return quote

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        results = []
        for symbol in symbols:
            results.append(await self.get_quote(symbol))
        return results
