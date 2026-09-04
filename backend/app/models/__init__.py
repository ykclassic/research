from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.execution import ExecutionAuthorization, ExecutionMode, ExecutionRequest, ExecutionResult, OrderRequest, OrderStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, TechnicalAnalysisResult, Timeframe
from app.models.market_structure import MarketStructureResult, StructureEvent, StructureStatus
from app.models.mtf import MTFBias, MTFResearchConclusion, MTFState, MTFTimeframeAnalysis, MultiTimeframeResult
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence, RegimeThresholds
from app.models.risk import PositionQualification, RiskPolicy, RiskQualificationStatus
from app.models.strategy import SignalDirection, StrategyDefinition, StrategyPortfolioResult, StrategySignal, StrategyStatus
from app.models.strategy_selection import QualificationStatus, StrategyQualification, StrategySelectionResult
from app.models.trade_lifecycle import ExitReason, PerformanceSummary, TradeLifecycleStatus, TradeOutcome, trade_from_execution
from app.providers.errors import ProviderErrorCode


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
    error_code: ProviderErrorCode | None = None
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    freshness_age_seconds: float | None = Field(default=None, ge=0)
    completeness_status: CompletenessStatus = CompletenessStatus.COMPLETE
    fallback_used: bool = False
    provider_attempts: tuple[str, ...] = ()
    provider_credits_used: int | None = Field(default=None, ge=0)
    provider_credits_remaining: int | None = Field(default=None, ge=0)


class ProviderStatus(BaseModel):
    provider: str
    configured: bool
    reachable: bool | None = None
    circuit_open: bool = False
    consecutive_failures: int = 0
    last_latency_ms: int | None = None
    last_error: str | None = None
    last_error_code: ProviderErrorCode | None = None
    credits_used: int | None = Field(default=None, ge=0)
    credits_remaining: int | None = Field(default=None, ge=0)
    usage_observed_at: datetime | None = None
    quote_budget_remaining: int | None = Field(default=None, ge=0)
    daily_quote_budget_remaining: int | None = Field(default=None, ge=0)
    message: str


__all__ = ["Candle", "CompletenessStatus", "FreshnessStatus", "OHLCVDataset", "ProviderErrorCode", "ProviderStatus", "Quote", "QuoteStatus", "TechnicalAnalysisResult", "Timeframe", "MarketRegime", "MarketRegimeResult", "RegimeEvidence", "RegimeThresholds", "SignalDirection", "StrategyDefinition", "StrategyPortfolioResult", "StrategySignal", "StrategyStatus", "MarketStructureResult", "StructureEvent", "StructureStatus", "MTFBias", "MTFResearchConclusion", "MTFState", "MTFTimeframeAnalysis", "MultiTimeframeResult", "QualificationStatus", "StrategyQualification", "StrategySelectionResult", "PositionQualification", "RiskPolicy", "RiskQualificationStatus", "ExecutionAuthorization", "ExecutionMode", "ExecutionRequest", "ExecutionResult", "OrderRequest", "OrderStatus", "ExitReason", "PerformanceSummary", "TradeLifecycleStatus", "TradeOutcome", "trade_from_execution"]
