from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.models.news import FundamentalEvent, NewsItem
from app.services.news_research import NewsResearchService

logger = logging.getLogger(__name__)


class ResilientNewsResearchService(NewsResearchService):
    """News research service that degrades gracefully when one provider feed fails."""

    async def _gather(
        self,
        symbol: str | None,
        start: datetime,
        end: datetime,
    ) -> tuple[list[NewsItem], list[FundamentalEvent], list[FundamentalEvent]]:
        results = await asyncio.gather(
            self._fetch_news(symbol, start, end),
            self._fetch_earnings(start, end, symbol),
            self._fetch_economic(start, end),
            return_exceptions=True,
        )

        names = ("news", "earnings", "economic")
        normalized: list[object] = []
        for name, result in zip(names, results, strict=True):
            if isinstance(result, Exception):
                # Never log the exception itself: HTTP client exceptions can contain
                # the authenticated Finnhub URL and therefore the API token.
                logger.warning("Finnhub %s feed unavailable; continuing with partial research", name)
                normalized.append([])
            else:
                normalized.append(result)

        news = normalized[0] if isinstance(normalized[0], list) else []
        earnings = normalized[1] if isinstance(normalized[1], list) else []
        economic = normalized[2] if isinstance(normalized[2], list) else []
        return news, earnings, economic


news_research = ResilientNewsResearchService()
