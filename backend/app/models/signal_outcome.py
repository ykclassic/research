from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SignalOutcomeStatus(str, Enum):
    PENDING = "PENDING"
    TARGET_HIT = "TARGET_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    AMBIGUOUS = "AMBIGUOUS"


class SignalAuditSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    symbol: str
    signal: str
    score: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    dispatched_at: datetime
    entry_price: float = Field(gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    target_price: float | None = Field(default=None, gt=0)
    provider: str
    timeframe: str
    signal_engine_version: str
    calculated_at: datetime
    latest_candle_timestamp: datetime


class SignalOutcomeRecord(SignalAuditSnapshot):
    target_tagged_at: datetime | None = None
    stop_tagged_at: datetime | None = None
    target_tag_latency_seconds: float | None = Field(default=None, ge=0)
    stop_tag_latency_seconds: float | None = Field(default=None, ge=0)
    first_touch_price: float | None = Field(default=None, gt=0)
    first_touch_timestamp: datetime | None = None
    outcome: SignalOutcomeStatus = SignalOutcomeStatus.PENDING
    observed_at: datetime | None = None
    observation_candle_timestamp: datetime | None = None
    observation_source: str | None = None
    coverage_warning: str | None = None
