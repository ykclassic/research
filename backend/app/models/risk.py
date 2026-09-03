from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.strategy import SignalDirection
from app.models.strategy_selection import StrategySelectionResult


class RiskQualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


class RiskPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = "1.0.0"
    risk_per_trade: float = Field(default=0.0075, gt=0, le=0.02)
    stop_atr_multiplier: float = Field(default=1.5, gt=0)
    minimum_reward_risk: float = Field(default=2.0, ge=1.0)


class PositionQualification(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    generated_at: datetime
    strategy_selection: StrategySelectionResult
    status: RiskQualificationStatus
    risk_policy: RiskPolicy
    account_equity: float = Field(gt=0)
    risk_amount: float = Field(ge=0)
    entry_price: float = Field(gt=0)
    atr: float = Field(gt=0)
    stop_distance: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    position_size: float = Field(gt=0)
    reward_risk: float = Field(ge=0)
    reasons: tuple[str, ...] = ()
