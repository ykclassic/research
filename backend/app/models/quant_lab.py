from __future__ import annotations

from datetime import datetime
from enum import Enum
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, Field

from app.models.market import Timeframe


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class StrategyRule(BaseModel):
    model_config = ConfigDict(frozen=True)
    field: str = Field(min_length=1, max_length=120)
    operator: str = Field(pattern="^(eq|neq|gt|gte|lt|lte|contains)$")
    value: object


class StrategyDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(default="1", min_length=1, max_length=64)
    entry_rules: tuple[StrategyRule, ...] = ()
    exit_rules: tuple[StrategyRule, ...] = ()
    direction: Side = Side.LONG
    timeframe: Timeframe = Timeframe.HOUR_1


class ExecutionAssumptions(BaseModel):
    model_config = ConfigDict(frozen=True)
    commission_bps: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0)
    spread_bps: float = Field(default=0, ge=0)
    position_size: float = Field(default=1, gt=0)


class ExperimentSpec(BaseModel):
    """Immutable, fully reproducible input contract for one quant experiment."""

    model_config = ConfigDict(frozen=True)
    dataset_version: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    parameters: dict[str, object] = Field(default_factory=dict)
    costs: dict[str, float] = Field(default_factory=dict)
    execution: ExecutionAssumptions = Field(default_factory=ExecutionAssumptions)
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime

    @property
    def spec_hash(self) -> str:
        payload = self.model_dump(mode="json")
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class TradeResult(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    model_config = ConfigDict(frozen=True)
    trades: int
    net_pnl: float
    expectancy: float
    profit_factor: float | None
    win_rate: float
    max_drawdown: float
    average_r: float
    average_mae: float = 0.0
    average_mfe: float = 0.0
    r_distribution: tuple[float, ...] = ()
    regime_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)
    timeframe_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    experiment_id: str
    spec_hash: str
    metrics: BacktestMetrics
    trades: tuple[TradeResult, ...]
    anti_overfit_checks: dict[str, bool]
    warnings: tuple[str, ...] = ()


class PaperTrade(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    experiment_id: str | None = None
    status: str = "OPEN"


class PaperPortfolio(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    base_currency: str
    starting_equity: float
    equity: float
    drawdown: float
    created_at: datetime


class StrategyDiagnosis(BaseModel):
    model_config = ConfigDict(frozen=True)
    performance_decay: float | None = None
    concentration: dict[str, float] = Field(default_factory=dict)
    unstable_parameters: tuple[str, ...] = ()
    sample_weakness: bool = False
    regime_deterioration: dict[str, float] = Field(default_factory=dict)

class WalkForwardWindow(BaseModel):
    model_config = ConfigDict(frozen=True)
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime

class WalkForwardResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    windows: tuple[WalkForwardWindow, ...]
    oos_trades: int
    oos_net_pnl: float
    oos_expectancy: float
    warnings: tuple[str, ...] = ()

class MonteCarloResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    simulations: int
    seed: int
    median_pnl: float
    p05_pnl: float
    p95_pnl: float
    probability_of_loss: float
    max_drawdown_p95: float

class ParameterSensitivityResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    parameter: str
    values: tuple[float, ...]
    net_pnl: tuple[float, ...]
    expectancy: tuple[float, ...]
    stable: bool

class RobustnessResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    walk_forward: WalkForwardResult
    monte_carlo: MonteCarloResult
    sensitivities: tuple[ParameterSensitivityResult, ...]
    scorecard: dict[str, bool]
    warnings: tuple[str, ...] = ()

class PaperBacktestComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    experiment_id: str
    paper_trade_count: int
    backtest_trade_count: int
    paper_net_pnl: float
    backtest_net_pnl: float
    pnl_drift: float
    trade_count_drift: float
    win_rate_drift: float | None = None
    status: str

class StrategyBuilderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(default='1', min_length=1, max_length=64)
    entry_rules: tuple[StrategyRule, ...] = ()
    exit_rules: tuple[StrategyRule, ...] = ()
    direction: Side = Side.LONG
    timeframe: Timeframe = Timeframe.HOUR_1
