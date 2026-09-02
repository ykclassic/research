from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.market import CompletenessStatus, FreshnessStatus, Timeframe


class MarketRegime(str, Enum):
    STRONG_TREND_UP = "STRONG_TREND_UP"
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"
    WEAK_TREND = "WEAK_TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNKNOWN = "UNKNOWN"


class RegimeThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)
    adx_strong: float = Field(default=25.0, ge=0)
    persistence_strong: float = Field(default=0.70, ge=0, le=1)
    persistence_weak: float = Field(default=0.50, ge=0, le=1)
    directional_ratio_strong: float = Field(default=0.55, ge=0, le=1)
    directional_ratio_weak: float = Field(default=0.25, ge=0, le=1)
    volatility_high_percentile: float = Field(default=0.80, ge=0, le=1)
    volatility_low_percentile: float = Field(default=0.20, ge=0, le=1)

    @model_validator(mode="after")
    def validate_ordering(self) -> RegimeThresholds:
        if self.persistence_strong <= self.persistence_weak:
            raise ValueError("persistence_strong must exceed persistence_weak.")
        if self.directional_ratio_strong <= self.directional_ratio_weak:
            raise ValueError("directional_ratio_strong must exceed directional_ratio_weak.")
        if self.volatility_high_percentile <= self.volatility_low_percentile:
            raise ValueError("volatility_high_percentile must exceed volatility_low_percentile.")
        return self


class RegimeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    price: float = Field(gt=0)
    ema_50: float | None
    ema_200: float | None
    price_above_ema_200: bool | None
    ema_50_above_ema_200: bool | None
    adx: float | None = Field(default=None, ge=0)
    atr: float | None = Field(default=None, ge=0)
    atr_percent: float | None
    atr_percentile: float | None = Field(default=None, ge=0, le=1)
    bb_width: float | None = Field(default=None, ge=0)
    bb_width_percentile: float | None = Field(default=None, ge=0, le=1)
    trend_direction: str
    trend_persistence: float = Field(ge=0, le=1)
    directional_move_ratio: float = Field(ge=0, le=1)


class MarketRegimeResult(BaseModel):
    """Canonical deterministic regime result with market-data quality metadata."""

    model_config = ConfigDict(frozen=True)
    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    provider_timestamp: datetime | None
    latest_candle_timestamp: datetime
    candle_count: int = Field(ge=1)
    regime: MarketRegime
    confidence: float = Field(ge=0, le=1)
    evidence: RegimeEvidence
    thresholds: RegimeThresholds
    rule_id: str
    rule: str
    request_latency_ms: int | None = Field(default=None, ge=0)
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    freshness_age_seconds: float | None = Field(default=None, ge=0)
    completeness_status: CompletenessStatus = CompletenessStatus.UNKNOWN
    fallback_used: bool = False
    provider_attempts: tuple[str, ...] = ()
    cache_hit: bool = False
