from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.models.market import Timeframe
from app.models.news import (
    EventType,
    FundamentalEvent,
    MarketReaction,
    NewsCorrelation,
    NewsItem,
    NewsResearchResponse,
    SentimentLabel,
    TechnicalRegimeContext,
)
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime
from app.symbols import SYMBOLS, normalize_symbol
from app.providers.orchestrator import market_data


_POSITIVE = {
    "beat", "beats", "bullish", "growth", "upgrade", "upgraded", "surge", "surged",
    "strong", "record", "profit", "profits", "outperform", "approval", "approved",
    "partnership", "win", "wins", "positive", "raises", "raised", "increase", "increased",
}
_NEGATIVE = {
    "miss", "misses", "bearish", "decline", "declined", "downgrade", "downgraded", "fall",
    "fell", "drop", "dropped", "weak", "loss", "losses", "lawsuit", "investigation", "fine",
    "recall", "warning", "cuts", "cut", "negative", "decrease", "decreased", "layoff", "bankruptcy",
}
_REGULATORY = {
    "sec", "fda", "ftc", "doj", "cftc", "finra", "regulator", "regulatory", "antitrust",
    "lawsuit", "investigation", "fine", "sanction", "compliance", "approval", "approved", "ban",
    "license", "licence", "enforcement",
}
_MACRO = {
    "federal reserve", "fed", "ecb", "boe", "boj", "central bank", "interest rate", "rate cut",
    "rate hike", "inflation", "cpi", "ppi", "gdp", "unemployment", "payrolls", "jobs report",
    "nonfarm", "pmi", "retail sales", "consumer confidence", "industrial production", "yield",
    "treasury", "tariff", "trade balance",
}
_EARNINGS = {
    "earnings", "eps", "revenue", "quarter", "guidance", "profit", "loss", "fiscal year",
    "results", "financial results", "outlook",
}


class NewsResearchService:
    base_url = "https://finnhub.io/api/v1"

    @property
    def configured(self) -> bool:
        return bool(settings.finnhub_api_key.strip())

    async def _get(self, path: str, params: dict[str, str]) -> object:
        if not self.configured:
            raise RuntimeError("FINNHUB_API_KEY is not configured.")
        query = dict(params)
        query["token"] = settings.finnhub_api_key
        timeout = httpx.Timeout(settings.provider_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{self.base_url}/{path}", params=query)
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        return payload

    @staticmethod
    def _date(value: datetime) -> str:
        return value.astimezone(timezone.utc).date().isoformat()

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text)}

    @classmethod
    def _sentiment(cls, text: str) -> tuple[SentimentLabel, float]:
        tokens = cls._tokens(text)
        positive = len(tokens & _POSITIVE)
        negative = len(tokens & _NEGATIVE)
        total = positive + negative
        if total == 0:
            return SentimentLabel.NEUTRAL, 0.0
        score = max(-1.0, min(1.0, (positive - negative) / total))
        if score > 0.15:
            return SentimentLabel.POSITIVE, score
        if score < -0.15:
            return SentimentLabel.NEGATIVE, score
        return SentimentLabel.NEUTRAL, score

    @classmethod
    def _event_type(cls, text: str, category: str = "") -> EventType:
        lower = text.lower()
        if any(term in lower for term in _REGULATORY):
            return EventType.REGULATORY
        if any(term in lower for term in _MACRO):
            return EventType.MACRO
        if any(term in lower for term in _EARNINGS):
            return EventType.EARNINGS
        if category.lower() in {"forex", "economic"}:
            return EventType.ECONOMIC
        if any(term in lower for term in {"acquire", "acquisition", "merger", "merges", "appoints", "appointed", "buyback", "dividend"}):
            return EventType.CORPORATE
        return EventType.NEWS

    @staticmethod
    def _known_entities(related: str, requested_symbol: str | None) -> tuple[str, ...]:
        values: set[str] = set()
        known = {symbol.upper() for symbol in SYMBOLS}
        related_tokens = [item.strip().upper() for item in re.split(r"[,;\s]+", related or "") if item.strip()]
        for token in related_tokens:
            if token in known:
                values.add(token)
        if requested_symbol and requested_symbol.upper() in known:
            values.add(requested_symbol.upper())
        return tuple(sorted(values))

    @classmethod
    def _news_item(cls, row: dict, requested_symbol: str | None) -> NewsItem | None:
        published_at = cls._timestamp(row.get("datetime"))
        headline = str(row.get("headline") or "").strip()
        if published_at is None or not headline:
            return None
        summary = str(row.get("summary") or "").strip()
        text = f"{headline} {summary}"
        entities = cls._known_entities(str(row.get("related") or ""), requested_symbol)
        sentiment, sentiment_score = cls._sentiment(text)
        category = str(row.get("category") or "")
        event_type = cls._event_type(text, category)
        raw_id = str(row.get("id") or row.get("url") or f"{headline}|{published_at.isoformat()}")
        news_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:24]
        return NewsItem(
            id=news_id,
            headline=headline,
            summary=summary,
            source=str(row.get("source") or "Finnhub"),
            source_url=str(row.get("url")) if row.get("url") else None,
            published_at=published_at,
            related_entities=entities,
            affected_assets=entities,
            event_type=event_type,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
        )

    async def _fetch_news(self, symbol: str | None, start: datetime, end: datetime) -> list[NewsItem]:
        rows: object
        if symbol:
            mapping = normalize_symbol(symbol)
            if mapping.asset_class in {"stock", "etf"}:
                rows = await self._get("company-news", {"symbol": mapping.twelve_data, "from": self._date(start), "to": self._date(end)})
            else:
                rows = await self._get("news", {"category": "general"})
        else:
            rows = await self._get("news", {"category": "general"})
        if not isinstance(rows, list):
            return []
        items = [item for row in rows if isinstance(row, dict) for item in [self._news_item(row, symbol)] if item is not None]
        if symbol and normalize_symbol(symbol).asset_class not in {"stock", "etf"}:
            symbol_upper = symbol.upper()
            items = [item for item in items if symbol_upper in item.affected_assets or symbol_upper in item.headline.upper() or symbol_upper in item.summary.upper()]
        return sorted({item.id: item for item in items}.values(), key=lambda item: item.published_at, reverse=True)

    async def _fetch_earnings(self, start: datetime, end: datetime, symbol: str | None) -> list[FundamentalEvent]:
        rows = await self._get("calendar/earnings", {"from": self._date(start), "to": self._date(end)})
        if not isinstance(rows, dict):
            return []
        raw = rows.get("earningsCalendar", [])
        if not isinstance(raw, list):
            return []
        target = symbol.upper() if symbol else None
        result: list[FundamentalEvent] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            row_symbol = str(row.get("symbol") or "").upper()
            if target and row_symbol != target:
                continue
            date_value = str(row.get("date") or "")
            if not date_value:
                continue
            try:
                timestamp = datetime.fromisoformat(date_value).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            actual = row.get("epsActual")
            estimate = row.get("epsEstimate")
            surprise = row.get("epsSurprise")
            title = f"{row_symbol} earnings"
            result.append(FundamentalEvent(
                id=f"earnings:{row_symbol}:{date_value}:{row.get('quarter')}:{row.get('year')}",
                event_type=EventType.EARNINGS,
                title=title,
                description="Scheduled or reported earnings event from Finnhub.",
                event_timestamp=timestamp,
                affected_assets=(row_symbol,) if row_symbol in SYMBOLS else (),
                actual=actual,
                estimate=estimate,
                previous=row.get("revenueEstimate"),
                surprise=surprise,
            ))
        return result

    async def _fetch_economic(self, start: datetime, end: datetime) -> list[FundamentalEvent]:
        rows = await self._get("calendar/economic", {"from": self._date(start), "to": self._date(end)})
        if not isinstance(rows, dict):
            return []
        raw = rows.get("economicCalendar", [])
        if not isinstance(raw, list):
            return []
        result: list[FundamentalEvent] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            timestamp = self._timestamp(row.get("time"))
            if timestamp is None:
                date_value = str(row.get("date") or "")
                try:
                    timestamp = datetime.fromisoformat(date_value).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            title = str(row.get("event") or row.get("name") or "Economic event")
            event_type = EventType.MACRO if any(term in title.lower() for term in _MACRO) else EventType.ECONOMIC
            result.append(FundamentalEvent(
                id=f"economic:{row.get('eventId') or hashlib.sha1(f'{title}|{timestamp.isoformat()}'.encode()).hexdigest()[:16]}",
                event_type=event_type,
                title=title,
                description=f"Economic calendar event; impact={row.get('impact') or 'unknown'}.",
                event_timestamp=timestamp,
                country=str(row.get("country")) if row.get("country") else None,
                importance=str(row.get("impact")) if row.get("impact") else None,
                actual=row.get("actual"),
                estimate=row.get("estimate"),
                previous=row.get("prev"),
            ))
        return result

    @staticmethod
    def _reaction(dataset, published_at: datetime) -> MarketReaction:
        candles = list(dataset.candles)
        before = [candle for candle in candles if candle.timestamp <= published_at]
        target_time = published_at + timedelta(hours=1)
        after = [candle for candle in candles if published_at < candle.timestamp <= target_time]
        if not before or not after:
            return MarketReaction(timeframe="1h")
        baseline = before[-1]
        reaction = after[-1]
        change = reaction.close - baseline.close
        percent = (change / baseline.close * 100) if baseline.close else None
        return MarketReaction(
            baseline_timestamp=baseline.timestamp,
            reaction_timestamp=reaction.timestamp,
            baseline_price=baseline.close,
            reaction_price=reaction.close,
            absolute_change=change,
            percent_change=percent,
            direction="UP" if change > 0 else "DOWN" if change < 0 else "FLAT",
            timeframe="1h",
        )

    async def _correlate(self, news: list[NewsItem]) -> list[NewsCorrelation]:
        selected = [item for item in news if item.affected_assets][:8]
        assets = sorted({asset for item in selected for asset in item.affected_assets if asset in SYMBOLS})
        if not assets:
            return []
        datasets = {}
        regimes = {}
        now = datetime.now(timezone.utc)
        for asset in assets:
            try:
                mapping = normalize_symbol(asset)
                dataset = await market_data.get_candles(mapping.internal, Timeframe.MINUTE_5, 300, start_date=now - timedelta(days=1), end_date=now)
                datasets[asset] = dataset
                completed = dataset.completed_candles
                if len(completed) >= MINIMUM_CANDLES:
                    regime = detect_regime(await market_data.get_candles(mapping.internal, Timeframe.HOUR_1, 250))
                    regimes[asset] = TechnicalRegimeContext(
                        regime=regime.regime.value,
                        confidence=regime.confidence,
                        trend_direction=regime.evidence.trend_direction,
                        latest_candle_timestamp=regime.latest_candle_timestamp,
                    )
            except (RuntimeError, ValueError):
                continue
        result: list[NewsCorrelation] = []
        for item in selected:
            for asset in item.affected_assets:
                if asset not in datasets:
                    continue
                result.append(NewsCorrelation(
                    news_id=item.id,
                    news_headline=item.headline,
                    event_type=item.event_type,
                    affected_asset=asset,
                    published_at=item.published_at,
                    sentiment=item.sentiment,
                    market_reaction=self._reaction(datasets[asset], item.published_at),
                    technical_regime=regimes.get(asset),
                ))
        return result

    async def research(self, symbol: str | None = None, days: int = 1, limit: int = 25) -> NewsResearchResponse:
        if symbol:
            symbol = normalize_symbol(symbol).internal
        days = max(1, min(days, 7))
        limit = max(1, min(limit, 50))
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        news, earnings, economic = await self._gather(symbol, start, end)
        news = news[:limit]
        events = sorted(earnings + economic, key=lambda item: item.event_timestamp, reverse=True)[:limit]
        correlations = await self._correlate(news)
        coverage = {
            "news": len(news),
            "earnings": sum(item.event_type == EventType.EARNINGS for item in events),
            "economic": sum(item.event_type == EventType.ECONOMIC for item in events),
            "macro": sum(item.event_type == EventType.MACRO for item in events),
            "regulatory": sum(item.event_type == EventType.REGULATORY for item in news),
            "correlations": len(correlations),
        }
        return NewsResearchResponse(
            symbol=symbol,
            generated_at=end,
            news=tuple(news),
            fundamental_events=tuple(events),
            correlations=tuple(correlations),
            coverage=coverage,
        )

    async def _gather(self, symbol: str | None, start: datetime, end: datetime):
        import asyncio
        news_task = self._fetch_news(symbol, start, end)
        earnings_task = self._fetch_earnings(start, end, symbol)
        economic_task = self._fetch_economic(start, end)
        news, earnings, economic = await asyncio.gather(news_task, earnings_task, economic_task)
        return news, earnings, economic


news_research = NewsResearchService()
