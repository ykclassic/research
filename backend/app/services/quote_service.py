from __future__ import annotations

import asyncio

from app.models import Quote, QuoteStatus
from app.models.market import CompletenessStatus
from app.providers.kraken_public import KrakenPublicProvider
from app.providers.orchestrator import MarketDataOrchestrator, market_data
from app.services.forex_quote_fallback import get_forex_quote
from app.services.resilient_market_data import ResilientMarketDataOrchestrator
from app.symbols import normalize_symbol


class QuoteService:
    """Application-level quote boundary with bounded dashboard latency.

    Crypto dashboard quotes use Kraken's credential-free batch ticker path in
    production so the 10-pair crypto universe does not consume Twelve Data
    credits or wait on unrelated stock/forex fallback providers. Non-crypto
    quotes remain on the canonical provider orchestrator with a hard response
    budget so the dashboard never waits through the entire provider chain.
    """

    DASHBOARD_PROVIDER_TIMEOUT_SECONDS = 8.0
    FOREX_FALLBACK_TIMEOUT_SECONDS = 2.0

    def __init__(self, orchestrator: MarketDataOrchestrator | None = None) -> None:
        self._using_production_orchestrator = orchestrator is None
        self.orchestrator = ResilientMarketDataOrchestrator(orchestrator or market_data)
        self.crypto_provider = KrakenPublicProvider()
        # Compatibility seam: existing tests and internal callers can inject a
        # provider-shaped object while the production boundary remains the
        # orchestrator proxy.
        self.provider = self.orchestrator

    @staticmethod
    def _unavailable_quote(symbol: str, reason: str) -> Quote:
        mapping = normalize_symbol(symbol)
        return Quote(
            symbol=mapping.internal,
            provider_symbol=mapping.twelve_data,
            status=QuoteStatus.UNAVAILABLE,
            source=None,
            error=reason,
            fallback_used=True,
            provider_attempts=(),
            completeness_status=CompletenessStatus.UNKNOWN,
        )

    async def _get_crypto_quote(
        self,
        symbol: str,
        force_refresh: bool,
        excluded_providers: set[str] | None,
    ) -> Quote:
        if not self._using_production_orchestrator or (excluded_providers and "kraken_public" in excluded_providers):
            return await self.orchestrator.get_quote(
                symbol,
                force_refresh=force_refresh,
                excluded_providers=excluded_providers,
            )
        try:
            return await self.crypto_provider.get_quote(symbol)
        except Exception as exc:
            try:
                return await asyncio.wait_for(
                    self.orchestrator.get_quote(
                        symbol,
                        force_refresh=force_refresh,
                        excluded_providers=excluded_providers,
                    ),
                    timeout=self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                return self._unavailable_quote(symbol, f"Crypto quote providers exceeded the {self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS:.0f}s response budget: {exc}")

    async def get_quote(
        self,
        symbol: str,
        force_refresh: bool = False,
        excluded_providers: set[str] | None = None,
    ) -> Quote:
        mapping = normalize_symbol(symbol)
        if mapping.asset_class == "crypto":
            quote = await self._get_crypto_quote(symbol, force_refresh, excluded_providers)
        else:
            try:
                quote = await asyncio.wait_for(
                    self.orchestrator.get_quote(
                        symbol,
                        force_refresh=force_refresh,
                        excluded_providers=excluded_providers,
                    ),
                    timeout=self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                quote = self._unavailable_quote(
                    symbol,
                    f"Market-data providers exceeded the {self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS:.0f}s response budget.",
                )

        if quote.status == QuoteStatus.UNAVAILABLE and mapping.asset_class == "forex":
            try:
                fallback = await asyncio.wait_for(
                    get_forex_quote(symbol),
                    timeout=self.FOREX_FALLBACK_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                fallback = None
            if fallback is not None:
                return fallback
        return quote

    async def get_quotes(self, symbols: list[str], force_refresh: bool = False) -> list[Quote]:
        if not symbols:
            return []

        crypto_symbols = [
            symbol for symbol in symbols if normalize_symbol(symbol).asset_class == "crypto"
        ]
        non_crypto_symbols = [
            symbol for symbol in symbols if normalize_symbol(symbol).asset_class != "crypto"
        ]

        async def fetch_crypto() -> list[Quote]:
            if not crypto_symbols:
                return []
            if not self._using_production_orchestrator:
                return await self.orchestrator.get_quotes(crypto_symbols, force_refresh=force_refresh)
            try:
                return await self.crypto_provider.get_quotes(crypto_symbols)
            except Exception as exc:
                try:
                    return await asyncio.wait_for(
                        self.orchestrator.get_quotes(crypto_symbols, force_refresh=force_refresh),
                        timeout=self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    return [
                        self._unavailable_quote(
                            symbol,
                            f"Crypto quote providers exceeded the {self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS:.0f}s response budget: {exc}",
                        )
                        for symbol in crypto_symbols
                    ]

        async def fetch_non_crypto() -> list[Quote]:
            if not non_crypto_symbols:
                return []
            try:
                quotes = await asyncio.wait_for(
                    self.orchestrator.get_quotes(non_crypto_symbols, force_refresh=force_refresh),
                    timeout=self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                quotes = [
                    self._unavailable_quote(
                        symbol,
                        f"Market-data providers exceeded the {self.DASHBOARD_PROVIDER_TIMEOUT_SECONDS:.0f}s response budget.",
                    )
                    for symbol in non_crypto_symbols
                ]
            forex_indexes = [
                index
                for index, quote in enumerate(quotes)
                if quote.status == QuoteStatus.UNAVAILABLE
                and normalize_symbol(quote.symbol).asset_class == "forex"
            ]
            if forex_indexes:
                async def bounded_forex(symbol: str) -> Quote | None:
                    try:
                        return await asyncio.wait_for(
                            get_forex_quote(symbol),
                            timeout=self.FOREX_FALLBACK_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        return None

                fallbacks = await asyncio.gather(
                    *(bounded_forex(quotes[index].symbol) for index in forex_indexes)
                )
                for index, fallback in zip(forex_indexes, fallbacks):
                    if fallback is not None:
                        quotes[index] = fallback
            return quotes

        crypto_quotes, non_crypto_quotes = await asyncio.gather(
            fetch_crypto(),
            fetch_non_crypto(),
        )
        by_symbol = {
            normalize_symbol(quote.symbol).internal: quote
            for quote in [*crypto_quotes, *non_crypto_quotes]
        }
        return [
            by_symbol.get(
                normalize_symbol(symbol).internal,
                self._unavailable_quote(symbol, "No market-data result was returned."),
            )
            for symbol in symbols
        ]
