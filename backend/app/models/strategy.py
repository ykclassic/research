from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.market import Timeframe
from app.models.regime import MarketRegime


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class StrategyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


class StrategySignal(BaseModel):
    """Deterministic strategy output for one completed market snapshot."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    symbol: str
    timeframe: Timeframe
    generated_at: datetime
    source: str
    direction: SignalDirection
    confidence: float = Field(ge=0, le=1)
    status: StrategyStatus
    regime: MarketRegime
    regime_compatible: bool
    rationale: str = Field(min_length=1)
    indicators_used: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()


class StrategyDefinition(BaseModel):
    """Immutable metadata describing a strategy registered in the portfolio."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    supported_timeframes: tuple[Timeframe, ...]
    supported_regimes: tuple[MarketRegime, ...]
    enabled: bool = True


class StrategyPortfolioResult(BaseModel):
    """All independent strategy evaluations for one canonical snapshot.

    Phase 6 intentionally does not rank, select, blend, or allocate capital
    between strategies. That policy belongs to Phase 7.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    source: str
    generated_at: datetime
    regime: MarketRegime
    regime_confidence: float = Field(ge=0, le=1)
    strategies: tuple[StrategySignal, ...]
    active_strategy_count: int = Field(ge=0)
