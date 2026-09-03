from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, TechnicalAnalysisResult, Timeframe
from app.models.market_structure import MarketStructureResult, StructureEvent, StructureStatus
from app.models.mtf import MTFBias, MTFResearchConclusion, MTFState, MTFTimeframeAnalysis, MultiTimeframeResult
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence, RegimeThresholds
from app.models.strategy import SignalDirection, StrategyDefinition, StrategyPortfolioResult, StrategySignal, StrategyStatus
from app.models.strategy_selection import QualificationStatus, StrategyQualification, StrategySelectionResult

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
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    freshness_age_seconds: float | None = Field(default=None, ge=0)
    completeness_status: CompletenessStatus = CompletenessStatus.COMPLETE
    fallback_used: bool = False
    provider_attempts: tuple[str, ...] = ()

class ProviderStatus(BaseModel):
    provider: str
    configured: bool
    reachable: bool | None = None
    circuit_open: bool = False
    consecutive_failures: int = 0
    last_latency_ms: int | None = None
    message: str

__all__ = ["Candle", "CompletenessStatus", "FreshnessStatus", "OHLCVDataset", "ProviderStatus", "Quote", "QuoteStatus", "TechnicalAnalysisResult", "Timeframe", "MarketRegime", "MarketRegimeResult", "RegimeEvidence", "RegimeThresholds", "SignalDirection", "StrategyDefinition", "StrategyPortfolioResult", "StrategySignal", "StrategyStatus", "MarketStructureResult", "StructureEvent", "StructureStatus", "MTFBias", "MTFResearchConclusion", "MTFState", "MTFTimeframeAnalysis", "MultiTimeframeResult", "QualificationStatus", "StrategyQualification", "StrategySelectionResult"]
