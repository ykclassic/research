from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class PortfolioPositionCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    side: PositionSide
    quantity: float = Field(gt=0)
    average_entry_price: float = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


class PortfolioPosition(PortfolioPositionCreate):
    model_config = ConfigDict(frozen=True)
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class PortfolioPositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    position: PortfolioPosition
    current_price: float | None
    market_value: float
    unrealized_pnl: float | None
    pnl_percent: float | None
    quote_status: str
    quote_timestamp: datetime | None


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    calculated_at: datetime
    position_count: int = Field(ge=0)
    invested_value: float = Field(ge=0)
    gross_exposure: float = Field(ge=0)
    net_exposure: float
    unrealized_pnl: float
    unrealized_pnl_percent: float | None
    max_position_concentration_percent: float = Field(ge=0, le=100)
    portfolio_drawdown_percent: float = Field(ge=0, le=100)
    risk_flags: tuple[str, ...]
    positions: tuple[PortfolioPositionSnapshot, ...]


class ScenarioRequest(BaseModel):
    price_change_percent: float = Field(ge=-100, le=1000)


class ScenarioResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    price_change_percent: float
    projected_unrealized_pnl: float
    projected_pnl_delta: float
    projected_gross_exposure: float
    affected_positions: int = Field(ge=0)


class RiskRewardRequest(BaseModel):
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    side: PositionSide


class RiskRewardResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    risk_per_unit: float = Field(ge=0)
    reward_per_unit: float = Field(ge=0)
    reward_risk_ratio: float = Field(ge=0)
    valid: bool
    reason: str
