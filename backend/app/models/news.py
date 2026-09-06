from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(str, Enum):
    NEWS = "NEWS"
    EARNINGS = "EARNINGS"
    ECONOMIC = "ECONOMIC"
    MACRO = "MACRO"
    REGULATORY = "REGULATORY"
    CORPORATE = "CORPORATE"
    OTHER = "OTHER"


class SentimentLabel(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class MarketReaction(BaseModel):
    model_config = ConfigDict(frozen=True)
    baseline_timestamp: datetime | None = None
    reaction_timestamp: datetime | None = None
    baseline_price: float | None = Field(default=None, ge=0)
    reaction_price: float | None = Field(default=None, ge=0)
    absolute_change: float | None = None
    percent_change: float | None = None
    direction: str = "UNKNOWN"
    timeframe: str = "1h"

    @field_validator("baseline_timestamp", "reaction_timestamp")
    @classmethod
    def timestamps_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("News reaction timestamps must be timezone-aware.")
        return value.astimezone(timezone.utc)


class TechnicalRegimeContext(BaseModel):
    regime: str
    confidence: float = Field(ge=0, le=1)
    trend_direction: str
    latest_candle_timestamp: datetime
    timeframe: str = "1h"


class NewsItem(BaseModel):
    id: str
    headline: str
    summary: str = ""
    source: str
    source_url: str | None = None
    published_at: datetime
    related_entities: tuple[str, ...] = ()
    affected_assets: tuple[str, ...] = ()
    event_type: EventType
    sentiment: SentimentLabel
    sentiment_score: float = Field(ge=-1, le=1)
    provider: str = "finnhub"

    @field_validator("published_at")
    @classmethod
    def publication_timestamp_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Publication timestamp must be timezone-aware.")
        return value.astimezone(timezone.utc)


class FundamentalEvent(BaseModel):
    id: str
    event_type: EventType
    title: str
    description: str = ""
    source: str = "Finnhub"
    source_url: str | None = None
    event_timestamp: datetime
    affected_assets: tuple[str, ...] = ()
    country: str | None = None
    importance: str | None = None
    actual: float | str | None = None
    estimate: float | str | None = None
    previous: float | str | None = None
    surprise: float | str | None = None
    provider: str = "finnhub"

    @field_validator("event_timestamp")
    @classmethod
    def event_timestamp_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Event timestamp must be timezone-aware.")
        return value.astimezone(timezone.utc)


class NewsCorrelation(BaseModel):
    news_id: str
    news_headline: str
    event_type: EventType
    affected_asset: str
    published_at: datetime
    sentiment: SentimentLabel
    market_reaction: MarketReaction
    technical_regime: TechnicalRegimeContext | None = None


class NewsResearchResponse(BaseModel):
    symbol: str | None = None
    generated_at: datetime
    provider: str = "finnhub"
    news: tuple[NewsItem, ...]
    fundamental_events: tuple[FundamentalEvent, ...]
    correlations: tuple[NewsCorrelation, ...]
    coverage: dict[str, int]
