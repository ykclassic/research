from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.market import Timeframe


class MarketRegime(str, Enum):
    STRONG_TREND_UP = "STRONG_TREND_UP"
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"
    WEAK_TREND = "WEAK_TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNKNOWN = "UNKNOWN"


class RegimeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: float
    ema_50: float | None
    ema_200: float | None
    price_above_ema_200: bool | None
    ema_50_above_ema_200: bool | None
    adx: float | None
    atr: float | None
    atr_percent: float | None
    atr_percentile: float | None
    bb_width: float | None
    bb_width_percentile: float | None
    trend_direction: str
    trend_persistence: float
    directional_move_ratio: float


class MarketRegimeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    latest_candle_timestamp: datetime
    candle_count: int = Field(ge=1)
    regime: MarketRegime
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: RegimeEvidence
    rule: str


__all__ = ["MarketRegime", "MarketRegimeResult", "RegimeEvidence"]
