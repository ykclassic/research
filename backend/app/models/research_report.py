from datetime import datetime

from pydantic import BaseModel, Field


class ReportTimeframe(BaseModel):
    timeframe: str
    trend: str
    momentum: str
    support: float | None = None
    resistance: float | None = None
    regime: str
    latest_candle_timestamp: datetime


class SMCStructure(BaseModel):
    bos: str | None = None
    fvg: list[str] = Field(default_factory=list)
    order_blocks: list[str] = Field(default_factory=list)
    liquidity: list[str] = Field(default_factory=list)


class FundamentalContext(BaseModel):
    news_count: int = 0
    macro_count: int = 0
    event_count: int = 0
    headlines: list[str] = Field(default_factory=list)


class MarketStatus(BaseModel):
    current_price: float
    change_24h_percent: float | None = None
    volume: float | None = None
    volatility_percent: float | None = None
    technical_structure: str
    trend: str
    momentum: str
    support: float | None = None
    resistance: float | None = None
    market_regime: str


class ResearchRequestConfiguration(BaseModel):
    """Auditable record of which research components and data rules were requested."""

    default_asset: str
    default_asset_class: str
    default_timeframe: str
    analysis_depth: str
    technical_analysis: bool
    market_structure: bool
    multi_timeframe: bool
    fundamental_analysis: bool
    news_analysis: bool
    ai_interpretation: bool
    maximum_data_age_seconds: int = 30
    reject_stale_data: bool = True
    require_completed_candles: bool = True
    allow_cached_data_fallback: bool = True


class ResearchReport(BaseModel):
    symbol: str
    generated_at: datetime
    request_configuration: ResearchRequestConfiguration | None = None
    market_status: MarketStatus
    indicators: dict[str, object] = Field(default_factory=dict)
    regime_snapshot: dict[str, object] = Field(default_factory=dict)
    smc_structure: SMCStructure
    multi_timeframe: list[ReportTimeframe]
    fundamental_context: FundamentalContext
    ai_interpretation: str | None = None
    bull_case: list[str]
    bear_case: list[str]
    key_risks: list[str]
    invalidation: list[str]
    overall_research_score: int = Field(ge=0, le=100)
    score_basis: dict[str, float] = Field(default_factory=dict)
    output_sections: dict[str, bool] = Field(default_factory=dict)
    display_timezone: str | None = None
