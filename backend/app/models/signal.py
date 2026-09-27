from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

class SignalReplayCandle(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: datetime
    open: float = Field(gt=0); high: float = Field(gt=0); low: float = Field(gt=0); close: float = Field(gt=0)
    volume: float = Field(ge=0); timeframe: str; source: str

class SignalDirection(str, Enum):
    NEUTRAL="NEUTRAL"; BUY="BUY"; STRONG_BUY="STRONG_BUY"; SELL="SELL"; STRONG_SELL="STRONG_SELL"
class SignalQualificationStatus(str, Enum):
    QUALIFIED="QUALIFIED"; REJECTED="REJECTED"
class RiskRewardStatus(str, Enum):
    AVAILABLE="AVAILABLE"; UNAVAILABLE="UNAVAILABLE"

class SignalComponent(BaseModel):
    model_config = ConfigDict(frozen=True)
    timeframe: str
    indicator_score: float = Field(ge=-1, le=1); smc_score: float = Field(ge=-1, le=1); combined_score: float = Field(ge=-1, le=1)
    evidence: tuple[str, ...] = ()

class CryptoSignal(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal_id: str = Field(default_factory=lambda: str(uuid4())); symbol: str; signal: SignalDirection
    score: float = Field(ge=-1, le=1)
    signal_strength: float = Field(default=0.0, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    calibrated_probability: float | None = Field(default=None, ge=0, le=1)
    confluence: float = Field(ge=0, le=1); confluence_families: tuple[str, ...] = ()
    expected_value_r: float | None = None
    risk_reward: float | None = Field(default=None, ge=0); risk_reward_status: RiskRewardStatus = RiskRewardStatus.UNAVAILABLE; risk_reward_reason: str | None = None
    structural_target: float | None = Field(default=None, gt=0); atr_minimum_target: float | None = Field(default=None, gt=0)
    price: float = Field(gt=0); entry_price: float = Field(gt=0); stop_loss: float | None = Field(default=None, gt=0); take_profit: float | None = Field(default=None, gt=0); atr: float | None = Field(default=None, gt=0); stop_distance: float | None = Field(default=None, gt=0)
    position_size: float | None = Field(default=None, gt=0); expected_cost: float = Field(default=0.0, ge=0); expected_slippage: float = Field(default=0.0, ge=0); expected_spread: float = Field(default=0.0, ge=0)
    calculated_at: datetime; latest_candle_timestamp: datetime; source: str; components: tuple[SignalComponent, ...]; evidence: tuple[str, ...] = ()
    research_eligible: bool = True; qualification_reasons: tuple[str, ...] = (); minimum_confidence: float = Field(ge=0, le=1); minimum_risk_reward: float = Field(ge=0); qualification_status: SignalQualificationStatus = SignalQualificationStatus.QUALIFIED
    mtf_bias: str | None = None; mtf_alignment: int | None = Field(default=None, ge=0, le=4); regime: str | None = None; regime_confidence: float | None = Field(default=None, ge=0, le=1); market_structure: str | None = None; liquidity_conditions: str | None = None; momentum: float | None = None; volatility: float | None = None; session: str | None = None
    strategy: str = "signal_engine"; signal_engine_version: str = "unknown"; feature_version: str = "signal-features-v2"; scoring_policy_version: str = "family-weighted-v2"; risk_policy_version: str = "risk-v2"; execution_model_version: str = "execution-v1"
    structural_conditions: dict[str, object] = Field(default_factory=dict); feature_families: dict[str, float] = Field(default_factory=dict); replay_candles: tuple[SignalReplayCandle, ...] = ()

class CryptoSignalList(BaseModel):
    model_config = ConfigDict(frozen=True)
    calculated_at: datetime; signals: tuple[CryptoSignal, ...]
