from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SignalDirection(str, Enum):
    NEUTRAL = "NEUTRAL"
    BUY = "BUY"
    STRONG_BUY = "STRONG_BUY"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class SignalQualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"


class RiskRewardStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class SignalComponent(BaseModel):
    model_config = ConfigDict(frozen=True)
    timeframe: str
    indicator_score: float = Field(ge=-1, le=1)
    smc_score: float = Field(ge=-1, le=1)
    combined_score: float = Field(ge=-1, le=1)
    evidence: tuple[str, ...] = ()


class CryptoSignal(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    signal: SignalDirection
    score: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    confluence: float = Field(ge=0, le=1)
    # None means a risk/reward ratio cannot be calculated because there is no
    # validated target. Zero is a real ratio and must not be used as a sentinel.
    risk_reward: float | None = Field(default=None, ge=0)
    risk_reward_status: RiskRewardStatus = RiskRewardStatus.UNAVAILABLE
    risk_reward_reason: str | None = None
    structural_target: float | None = Field(default=None, gt=0)
    atr_minimum_target: float | None = Field(default=None, gt=0)
    price: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    atr: float | None = Field(default=None, gt=0)
    calculated_at: datetime
    latest_candle_timestamp: datetime
    source: str
    components: tuple[SignalComponent, ...]
    evidence: tuple[str, ...] = ()
    research_eligible: bool = True
    qualification_reasons: tuple[str, ...] = ()
    minimum_confidence: float = Field(ge=0, le=1)
    minimum_risk_reward: float = Field(ge=0)
    qualification_status: SignalQualificationStatus = SignalQualificationStatus.QUALIFIED


class CryptoSignalList(BaseModel):
    model_config = ConfigDict(frozen=True)
    calculated_at: datetime
    signals: tuple[CryptoSignal, ...]
