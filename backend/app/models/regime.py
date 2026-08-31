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
    """Auditable measurements used by the deterministic regime classifier."""

    model_config = ConfigDict(frozen=True)

    price: float
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    price_above_ema_200: bool | None = None
    ema_50_above_ema_200: bool | None = None
    adx14: float | None = None
    atr14: float | None = None
    atr_percentile: float | None = Field(default=None, ge=0.0, le=100.0)
    bb_width: float | None = None
    bb_width_percentile: float | None = Field(default=None, ge=0.0, le=100.0)
    directional_return: float | None = None
    trend_persistence: float | None = Field(default=None, ge=0.0, le=1.0)
    structure_bias: str = "UNKNOWN"
    completed_candles: int = Field(ge=1)


class MarketRegimeResult(BaseModel):
    """Deterministic, provenance-aware market regime classification."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    latest_completed_candle_timestamp: datetime
    regime: MarketRegime
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: RegimeEvidence
    rationale: tuple[str, ...]
