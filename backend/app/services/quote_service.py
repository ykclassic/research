import asyncio

from app.models import Quote, QuoteStatus
from app.models.market import OHLCVDataset, Timeframe
from app.providers.orchestrator import MarketDataOrchestrator, market_data
from app.services.forex_quote_fallback import get_forex_quote
from app.symbols import normalize_symbol


class QuoteService:
    def __init__(self, orchestrator: MarketDataOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or market_data
        # Compatibility seam: existing tests and internal callers can inject a
        # provider-shaped object while the production boundary remains the
        # orchestrator.
        self.provider = self.orchestrator

    async def get_quote(self, symbol: str, force_refresh: bool = False, excluded_providers: set[str] | None = None) -> Quote:
        quote = await self.orchestrator.get_quote(symbol, force_refresh=force_refresh, excluded_providers=excluded_providers)
        if quote.status == QuoteStatus.UNAVAILABLE and normalize_symbol(symbol).asset_class == "forex":
            fallback = await get_forex_quote(symbol)
            if fallback is not None:
                return fallback
        return quote

    async def get_quotes(self, symbols: list[str], force_refresh: bool = False) -> list[Quote]:
        quotes = await self.orchestrator.get_quotes(symbols, force_refresh=force_refresh)
        forex_indexes = [
            index for index, quote in enumerate(quotes)
            if quote.status == QuoteStatus.UNAVAILABLE and normalize_symbol(quote.symbol).asset_class == "forex"
        ]
        if not forex_indexes:
            return quotes
        fallbacks = await asyncio.gather(*(get_forex_quote(quotes[index].symbol) for index in forex_indexes))
        for index, fallback in zip(forex_indexes, fallbacks):
            if fallback is not None:
                quotes[index] = fallback
        return quotes

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
        *,
        start_date=None,
        end_date=None,
    ) -> OHLCVDataset:
        """Retrieve canonical candles with one controlled recovery attempt.

        The production orchestrator intentionally owns provider health and
        circuit breaking. If every provider is temporarily rejected because a
        shared in-process circuit is open, a fresh orchestrator instance gives
        the request one isolated recovery attempt without changing the normal
        provider ordering or retrying indefinitely.
        """
        try:
            return await self.orchestrator.get_candles(
                symbol,
                timeframe,
                limit,
                start_date=start_date,
                end_date=end_date,
            )
        except (RuntimeError, asyncio.TimeoutError) as first_error:
            if start_date is not None or end_date is not None:
                raise
            recovery_orchestrator = MarketDataOrchestrator()
            try:
                return await recovery_orchestrator.get_candles(symbol, timeframe, limit)
            except Exception as recovery_error:
                raise first_error from recovery_error
