from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PortfolioExposure(BaseModel):
    symbol: str
    market_value: float
    weight_percent: float
    net_weight_percent: float
    side: str
    asset_class: str
    sector: str
    category: str


class CorrelationEntry(BaseModel):
    symbol: str
    correlation: float


class CorrelationCluster(BaseModel):
    cluster_id: str
    symbols: tuple[str, ...]
    average_pairwise_correlation: float | None


class RiskContribution(BaseModel):
    symbol: str
    exposure_percent: float
    volatility_percent: float | None
    risk_contribution_percent: float | None


class RegimeAlignment(BaseModel):
    symbol: str
    timeframe: str
    regime: str
    confidence: float
    alignment: str


class SignalExposure(BaseModel):
    symbol: str
    active_signals: int
    net_direction: str
    average_confidence: float | None
    regimes: tuple[str, ...]


class PortfolioIntelligence(BaseModel):
    model_config = ConfigDict(frozen=True)
    calculated_at: str
    exposures: tuple[PortfolioExposure, ...]
    asset_allocation: dict[str, float]
    sector_exposure: dict[str, float]
    category_exposure: dict[str, float]
    correlation_matrix: dict[str, tuple[CorrelationEntry, ...]]
    correlation_clusters: tuple[CorrelationCluster, ...]
    risk_contribution: tuple[RiskContribution, ...]
    regime_alignment: tuple[RegimeAlignment, ...]
    signal_exposure: tuple[SignalExposure, ...]
    changes: tuple[str, ...]
    risk_drivers: tuple[str, ...]
    alerts: tuple[str, ...]
    relevant_signals: tuple[str, ...]
    relevant_catalysts: tuple[str, ...]
    data_quality: tuple[str, ...]


class ScenarioRequestV2(BaseModel):
    scenario_type: str = Field(default="ASSET_SHOCK")
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    shock_percent: float = Field(default=0, ge=-100, le=1000)


class ScenarioImpact(BaseModel):
    symbol: str
    shock_percent: float
    pnl_delta: float
    exposure_delta: float


class PortfolioScenarioV2(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    assumptions: tuple[str, ...]
    projected_pnl_delta: float
    projected_unrealized_pnl: float
    projected_gross_exposure: float
    impacts: tuple[ScenarioImpact, ...]
    affected_positions: int
    data_quality: tuple[str, ...]
