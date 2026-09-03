from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.market import Timeframe


class MTFBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class MTFState(str, Enum):
    DAILY_BIAS = "DAILY_BIAS"
    H4_TREND = "H4_TREND"
    H1_PULLBACK = "H1_PULLBACK"
    H1_CONTINUATION = "H1_CONTINUATION"
    H1_REVERSAL = "H1_REVERSAL"
    H1_NEUTRAL = "H1_NEUTRAL"
    M15_BULLISH_BOS = "M15_BULLISH_BOS"
    M15_BEARISH_BOS = "M15_BEARISH_BOS"
    M15_CONFIRMATION = "M15_CONFIRMATION"
    M15_NEUTRAL = "M15_NEUTRAL"
    UNKNOWN = "UNKNOWN"


class MTFTimeframeAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)
    timeframe: Timeframe
    bias: MTFBias
    state: MTFState
    conclusion: str
    confidence: float = Field(ge=0, le=1)
    latest_candle_timestamp: datetime
    source: str
    candle_count: int = Field(ge=1)
    evidence: tuple[str, ...] = ()


class MTFResearchConclusion(BaseModel):
    model_config = ConfigDict(frozen=True)
    alignment_count: int = Field(ge=0, le=4)
    alignment_total: int = Field(default=4, ge=4, le=4)
    bias: MTFBias
    confidence: float = Field(ge=0, le=1)
    primary_setup: str
    invalidation: str
    conclusion: str


class MultiTimeframeResult(BaseModel):
    """Canonical deterministic Daily -> H4 -> H1 -> M15 research result."""

    model_config = ConfigDict(frozen=True)
    symbol: str
    calculated_at: datetime
    timeframes: tuple[MTFTimeframeAnalysis, ...]
    research: MTFResearchConclusion
