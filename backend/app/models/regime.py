from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    ema50: float | None = None
    ema200: float | None = None
    price_above_ema200: bool | None = None
    ema50_above_ema200: bool | None = None
    adx14: float | None = None
    atr14: float | None = None
    atr_percentile: float | None = None
    bb_width: float | None = None
    bb_width_percentile: float | None = None
    trend_persistence: float | None = None
    structure_direction: str = "UNKNOWN"
    higher_highs: int = Field(default=0, ge=0)
    higher_lows: int = Field(default=0, ge=0)
    lower_highs: int = Field(default=0, ge=0)
    lower_lows: int = Field(default=0, ge=0)

    @field_validator(
        "price", "ema50", "ema200", "adx14", "atr14", "atr_percentile",
        "bb_width", "bb_width_percentile", "trend_persistence"
    )
    @classmethod
    def finite_values(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("Regime evidence values must be finite.")
        return value


class MarketRegimeResult(BaseModel):
    """Canonical, immutable result of deterministic market-regime detection."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    source: str
    calculated_at: datetime
    latest_completed_candle_timestamp: datetime
    candle_count: int = Field(ge=1)
    regime: MarketRegime
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: RegimeEvidence
    ruleset_version: str = "5.1.0"

    @field_validator("calculated_at", "latest_completed_candle_timestamp")
    @classmethod
    def timestamps_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Regime timestamps must be timezone-aware.")
        return value.astimezone(timezone.utc)
