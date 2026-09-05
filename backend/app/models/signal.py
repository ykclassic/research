from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SignalDirection(str, Enum):
    NEUTRAL = "NEUTRAL"
    BUY = "BUY"
    STRONG_BUY = "STRONG_BUY"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class SignalComponent(BaseModel):
    model_config = ConfigDict(frozen=True)
    timeframe: str
    indicator_score: float = Field(ge=-1, le=1)
    smc_score: float = Field(ge=-1, le=1)
    combined_score: float = Field(ge=-1, le=1)
    evidence: tuple[str, ...] = ()


class CryptoSignal(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    signal: SignalDirection
    score: float = Field(ge=-1, le=1)
    confluence: float = Field(ge=0, le=1)
    price: float = Field(gt=0)
    calculated_at: datetime
    latest_candle_timestamp: datetime
    source: str
    components: tuple[SignalComponent, ...]
    evidence: tuple[str, ...] = ()
    research_eligible: bool = True


class CryptoSignalList(BaseModel):
    model_config = ConfigDict(frozen=True)
    calculated_at: datetime
    signals: tuple[CryptoSignal, ...]
