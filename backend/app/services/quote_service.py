import asyncio

from app.models import Quote
from app.providers.orchestrator import MarketDataOrchestrator, market_data


class QuoteService:
    def __init__(self, orchestrator: MarketDataOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or market_data

    async def get_quote(
        self,
        symbol: str,
        force_refresh: bool = False,
        excluded_providers: set[str] | None = None,
    ) -> Quote:
        return await self.orchestrator.get_quote(
            symbol,
            force_refresh=force_refresh,
            excluded_providers=excluded_providers,
        )

    async def get_quotes(
        self,
        symbols: list[str],
        force_refresh: bool = False,
    ) -> list[Quote]:
        return list(
            await asyncio.gather(
                *(
                    self.get_quote(symbol, force_refresh=force_refresh)
                    for symbol in symbols
                )
            )
        )
