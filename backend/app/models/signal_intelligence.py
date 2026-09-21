from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class SignalReplayCandle(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    timeframe: str
    source: str


class SignalIntelligenceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    signal_id: str
    revision: int = Field(ge=1)
    symbol: str
    direction: str
    confidence: float = Field(ge=0, le=1)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    target_price: float = Field(gt=0)
    risk_reward: float | None = Field(default=None, ge=0)
    timeframe: str
    mtf_bias: str | None = None
    mtf_alignment: int | None = Field(default=None, ge=0, le=4)
    regime: str | None = None
    regime_confidence: float | None = Field(default=None, ge=0, le=1)
    market_structure: str | None = None
    liquidity_conditions: str | None = None
    momentum: float | None = None
    volatility: float | None = None
    session: str | None = None
    strategy: str
    outcome: str
    dispatched_at: datetime
    target_timestamp: datetime | None = None
    stop_timestamp: datetime | None = None
    first_touch_timestamp: datetime | None = None
    r_result: float | None = None
    outcome_latency_seconds: float | None = None
    signal_engine_version: str
    evidence: tuple[str, ...] = ()
    replay_candles: tuple[SignalReplayCandle, ...] = ()
    structural_conditions: dict[str, object] = {}


class CalibrationBucket(BaseModel):
    model_config = ConfigDict(frozen=True)
    label: str
    lower: float
    upper: float | None
    sample_size: int
    observed_outcome_rate: float | None
    mean_r: float | None
    statistically_meaningful: bool
    note: str


class SignalCalibration(BaseModel):
    model_config = ConfigDict(frozen=True)
    minimum_sample_size: int
    total_samples: int
    buckets: tuple[CalibrationBucket, ...]


class SignalExplorerResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    total: int
    sample_size_note: str
    signals: tuple[SignalIntelligenceSnapshot, ...]


class SignalReplay(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal: SignalIntelligenceSnapshot
    chronological_states: tuple[dict[str, object], ...]
    outcome: str
    methodology_note: str
