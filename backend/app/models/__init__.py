from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.market import Candle, OHLCVDataset, TechnicalAnalysisResult, Timeframe
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence


class QuoteStatus(str, Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    MARKET_CLOSED = "MARKET_CLOSED"


class Quote(BaseModel):
    symbol: str
    provider_symbol: str
    price: float | None = Field(default=None, ge=0)
    currency: str | None = None
    timestamp: datetime | None = None
    provider_timestamp: datetime | None = None
    observed_at: datetime | None = None
    source: str | None = None
    status: QuoteStatus
    market_open: bool | None = None
    latency_ms: int | None = None
    cache_hit: bool = False
    error: str | None = None


class ProviderStatus(BaseModel):
    provider: str
    configured: bool
    reachable: bool | None = None
    message: str


__all__ = [
    "Candle",
    "MarketRegime",
    "MarketRegimeResult",
    "OHLCVDataset",
    "ProviderStatus",
    "Quote",
    "QuoteStatus",
    "RegimeEvidence",
    "TechnicalAnalysisResult",
    "Timeframe",
]
