from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.execution import ExecutionResult
from app.models.strategy import SignalDirection


class TradeLifecycleStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    AMBIGUOUS = "AMBIGUOUS"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    EXPIRED = "EXPIRED"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class TradeOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_id: str
    client_order_id: str
    broker_order_id: str | None = None
    symbol: str
    direction: SignalDirection
    strategy_id: str
    entry_price: float = Field(gt=0)
    exit_price: float | None = Field(default=None, gt=0)
    quantity: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    status: TradeLifecycleStatus
    exit_reason: ExitReason | None = None
    realized_pnl: float | None = None
    r_multiple: float | None = None
    entry_time: datetime
    exit_time: datetime | None = None


class PerformanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    strategy_id: str
    trade_count: int = Field(ge=0)
    closed_trade_count: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    total_pnl: float
    average_r: float
    expectancy_r: float
    profit_factor: float = Field(ge=0)


def trade_from_execution(execution: ExecutionResult) -> TradeOutcome:
    if execution.status.value != "FILLED" or not execution.broker_order_id:
        raise ValueError("Only filled executions can enter the trade lifecycle.")
    trade_id = f"TRADE-{execution.client_order_id}"
    entry_time = execution.executed_at or execution.generated_at
    return TradeOutcome(
        trade_id=trade_id,
        client_order_id=execution.client_order_id,
        broker_order_id=execution.broker_order_id,
        symbol=execution.symbol,
        direction=execution.direction,
        strategy_id=execution.strategy_id,
        entry_price=execution.fill_price or execution.requested_entry_price,
        quantity=execution.filled_quantity,
        stop_loss=execution.stop_loss,
        take_profit=execution.take_profit,
        status=TradeLifecycleStatus.OPEN,
        entry_time=entry_time,
    )
