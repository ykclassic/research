from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.risk import PositionQualification
from app.models.strategy import SignalDirection


class ExecutionMode(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderStatus(str, Enum):
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    FAILED = "FAILED"


class ExecutionAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved: bool = False
    approval_id: str | None = None
    approved_at: datetime | None = None
    expires_at: datetime | None = None


class OrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    direction: SignalDirection
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    strategy_id: str = Field(min_length=1)
    risk_policy_version: str = Field(min_length=1)
    execution_mode: ExecutionMode
    created_at: datetime


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str
    broker_order_id: str | None = None
    symbol: str
    direction: SignalDirection
    status: OrderStatus
    execution_mode: ExecutionMode
    requested_quantity: float
    filled_quantity: float = Field(default=0, ge=0)
    requested_entry_price: float
    fill_price: float | None = None
    stop_loss: float
    take_profit: float
    strategy_id: str
    generated_at: datetime
    executed_at: datetime | None = None
    message: str


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    position: PositionQualification
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    authorization: ExecutionAuthorization = ExecutionAuthorization()
    client_order_id: str | None = None
