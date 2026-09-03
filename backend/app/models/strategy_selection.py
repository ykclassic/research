from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.mtf import MTFBias, MultiTimeframeResult
from app.models.strategy import SignalDirection, StrategySignal


class QualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


class StrategyQualification(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    strategy_version: str
    direction: SignalDirection
    status: QualificationStatus
    score: float = Field(ge=0, le=1)
    mtf_bias: MTFBias
    mtf_alignment_count: int = Field(ge=0, le=4)
    mtf_gate_passed: bool
    reasons: tuple[str, ...] = ()


class StrategySelectionResult(BaseModel):
    """Canonical Phase 8 output: qualify, rank, and select; never allocate or execute."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    generated_at: datetime
    mtf: MultiTimeframeResult
    qualifications: tuple[StrategyQualification, ...]
    selected_strategy_id: str | None = None
    selected_direction: SignalDirection = SignalDirection.NEUTRAL
    selected_score: float = Field(default=0.0, ge=0, le=1)
    decision: str
    gate_version: str = "1.0.0"
