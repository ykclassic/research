from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class StrategyRule(BaseModel):
    field: str = Field(min_length=1, max_length=120)
    operator: str = Field(pattern="^(eq|neq|gt|gte|lt|lte|contains)$")
    value: object

class StrategyDefinition(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    version: int = Field(default=1, ge=1)
    entry_rules: tuple[StrategyRule, ...] = ()
    exit_rules: tuple[StrategyRule, ...] = ()
    direction: Side = Side.LONG
    timeframe: str = "1h"

class ExecutionAssumptions(BaseModel):
    commission_bps: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0)
    spread_bps: float = Field(default=0, ge=0)
    position_size: float = Field(default=1, gt=0)

class ExperimentSpec(BaseModel):
    dataset_version: str
    strategy_version: str
    feature_version: str
    parameters: dict[str, object] = Field(default_factory=dict)
    costs: dict[str, float] = Field(default_factory=dict)
    execution: ExecutionAssumptions = Field(default_factory=ExecutionAssumptions)
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime

class TradeResult(BaseModel):
    entry_time: datetime
    exit_time: datetime
    side: Side
    entry_price: float
    exit_price: float
    pnl: float
    r_multiple: float
    mae: float
    mfe: float
    regime: str | None = None
    timeframe: str

class BacktestMetrics(BaseModel):
    trades: int
    net_pnl: float
    expectancy: float
    profit_factor: float | None
    win_rate: float
    max_drawdown: float
    average_r: float
    r_distribution: tuple[float, ...] = ()
    regime_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)
    timeframe_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)

class BacktestResult(BaseModel):
    experiment_id: str
    metrics: BacktestMetrics
    trades: tuple[TradeResult, ...]
    anti_overfit_checks: dict[str, bool]
    warnings: tuple[str, ...] = ()

class PaperTrade(BaseModel):
    id: str
    portfolio_id: str
    symbol: str
    side: Side
    quantity: float
    entry_price: float
    entry_time: datetime
    exit_price: float | None = None
    exit_time: datetime | None = None
    pnl: float | None = None
    strategy_id: str | None = None
    signal_id: str | None = None
    status: str = "OPEN"

class PaperPortfolio(BaseModel):
    id: str
    name: str
    base_currency: str
    starting_equity: float
    equity: float
    drawdown: float
    created_at: datetime

class StrategyDiagnosis(BaseModel):
    performance_decay: float | None = None
    concentration: dict[str, float] = Field(default_factory=dict)
    unstable_parameters: tuple[str, ...] = ()
    sample_weakness: bool = False
    regime_deterioration: dict[str, float] = Field(default_factory=dict)
