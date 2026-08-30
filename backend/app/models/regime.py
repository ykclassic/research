from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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

    price_above_ema_200: bool | None = None
    ema_50_above_ema_200: bool | None = None
    ema_50_slope_pct: float | None = None
    adx14: float | None = None
    atr14: float | None = None
    atr_percentile: float | None = Field(default=None, ge=0, le=100)
    bb_width: float | None = None
    bb_width_percentile: float | None = Field(default=None, ge=0, le=100)
    trend_persistence: float | None = Field(default=None, ge=0, le=1)
    higher_highs: bool | None = None
    higher_lows: bool | None = None
    lower_highs: bool | None = None
    lower_lows: bool | None = None


class MarketRegimeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    source: str
    regime: MarketRegime
    confidence: float = Field(ge=0, le=1)
    calculated_at: datetime
    latest_candle_timestamp: datetime
    candle_count: int = Field(ge=1)
    evidence: RegimeEvidence
