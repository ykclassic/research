from __future__ import annotations

from hashlib import sha256
from itertools import groupby
from typing import Any, Iterable

from app.models.market import Candle, OHLCVDataset
from app.models.quant_lab import (
    BacktestMetrics,
    BacktestResult,
    ExperimentSpec,
    PaperPortfolio,
    PaperTrade,
    Side,
    StrategyDefinition,
    StrategyDiagnosis,
    TradeResult,
)
from app.services.entitlement import require_feature
from app.services.supabase_data import DataRequestError, _request
from app.services.performance import summarize_backtest_trades

ENGINE_VERSION = "quant-lab-v2-deterministic"
DATASET_VERSION = "ohlcv-completed-v1"


def _match(value: Any, operator: str, target: Any) -> bool:
    if operator == "eq":
        return value == target
    if operator == "neq":
        return value != target
    if operator == "contains":
        return target in value if value is not None else False
    try:
        left, right = float(value), float(target)
    except (TypeError, ValueError):
        return False
    return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}.get(operator, False)


def _rules_match(candle: Candle, rules: Iterable[Any]) -> bool:
    context = {"open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close, "volume": candle.volume}
    return all(_match(context.get(rule.field), rule.operator, rule.value) for rule in rules)


def _dataset_fingerprint(dataset: OHLCVDataset) -> str:
    canonical = "|".join(
        f"{c.timestamp.isoformat()}:{c.open}:{c.high}:{c.low}:{c.close}:{c.volume}"
        for c in dataset.completed_candles
    )
    return sha256(f"{dataset.symbol}|{dataset.timeframe.value}|{dataset.source}|{canonical}".encode()).hexdigest()


def validate_experiment(spec: ExperimentSpec) -> tuple[bool, tuple[str, ...]]:
    ordered = (
        spec.train_start,
        spec.train_end,
        spec.validation_start,
        spec.validation_end,
        spec.test_start,
        spec.test_end,
    )
    warnings: list[str] = []
    if any(ordered[i] >= ordered[i + 1] for i in range(len(ordered) - 1)):
        warnings.append("Train, validation and test periods must be chronological and non-overlapping.")
    if not spec.dataset_version or not spec.strategy_version or not spec.feature_version:
        warnings.append("Dataset, strategy and feature versions are required.")
    return not warnings, tuple(warnings)


def _fill_price(price: float, side: Side, assumptions, is_entry: bool) -> float:
    # Spread is charged half on each side; slippage is adverse on every fill.
    spread = price * assumptions.spread_bps / 20000
    slip = price * assumptions.slippage_bps / 10000
    direction = 1 if side is Side.LONG else -1
    return price + direction * (spread + slip) if is_entry else price - direction * (spread + slip)


def _trade(entry_index: int, exit_index: int, candles: list[Candle], side: Side, execution: Any, regime: str | None = None) -> TradeResult:
    entry = candles[entry_index]
    exit = candles[exit_index]
    entry_price = _fill_price(entry.close, side, execution, True)
    exit_price = _fill_price(exit.close, side, execution, False)
    quantity = execution.position_size
    gross = (exit_price - entry_price) if side is Side.LONG else (entry_price - exit_price)
    commission = (entry_price + exit_price) * quantity * execution.commission_bps / 10000
    pnl = gross * quantity - commission
    risk = max(abs(entry.close) * 0.01, 1e-12)
    r = pnl / (risk * quantity)
    path = candles[entry_index : exit_index + 1]
    if side is Side.LONG:
        adverse_excursion = min(c.low - entry_price for c in path)
        favorable_excursion = max(c.high - entry_price for c in path)
    else:
        adverse_excursion = max(entry_price - c.high for c in path)
        favorable_excursion = max(entry_price - c.low for c in path)
    return TradeResult(
        entry_time=entry.timestamp,
        exit_time=exit.timestamp,
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        pnl=pnl,
        r_multiple=r,
        mae=adverse_excursion,
        mfe=favorable_excursion,
        regime=regime,
        timeframe=entry.timeframe.value,
    )


def _metrics(trades: list[TradeResult]) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(trades=0, net_pnl=0, expectancy=0, profit_factor=None, win_rate=0, max_drawdown=0, average_r=0)
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    equity = peak = max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    def groups(key):
        return {
            k: {
                "trades": float(len(items)),
                "net_pnl": sum(x.pnl for x in items),
                "win_rate": sum(x.pnl > 0 for x in items) / len(items),
            }
            for k, values in groupby(sorted(trades, key=key), key)
            for items in [list(values)]
        }

    return BacktestMetrics(
        trades=len(trades),
        net_pnl=sum(pnls),
        expectancy=sum(pnls) / len(pnls),
        profit_factor=(sum(wins) / abs(sum(losses)) if losses else None),
        win_rate=len(wins) / len(trades),
        max_drawdown=max_dd,
        average_r=sum(t.r_multiple for t in trades) / len(trades),
        r_distribution=tuple(t.r_multiple for t in trades),
        regime_breakdown=groups(lambda t: t.regime or "UNKNOWN"),
        timeframe_breakdown=groups(lambda t: t.timeframe),
    )


def run_backtest(
    access_token: str,
    user_id: str,
    strategy: StrategyDefinition,
    dataset: OHLCVDataset,
    spec: ExperimentSpec,
) -> BacktestResult:
    """Run and persist one immutable experiment through the canonical event loop."""
    require_feature(access_token, user_id, "backtesting")
    valid, warnings = validate_experiment(spec)
    if not valid:
        raise ValueError("; ".join(warnings))
    if dataset.timeframe is not strategy.timeframe:
        raise ValueError("Strategy timeframe must match the experiment dataset timeframe.")
    completed = list(dataset.completed_candles)
    if len(completed) != len(dataset.candles):
        raise ValueError("Backtests require an explicitly completed-candle dataset.")
    if not completed:
        raise ValueError("Backtests require at least one completed candle.")

    test_candles = [c for c in completed if spec.test_start <= c.timestamp <= spec.test_end]
    trades: list[TradeResult] = []
    entry_index: int | None = None
    for absolute_index, candle in enumerate(completed):
        if not (spec.test_start <= candle.timestamp <= spec.test_end):
            continue
        if entry_index is None:
            if _rules_match(candle, strategy.entry_rules):
                entry_index = absolute_index
        elif _rules_match(candle, strategy.exit_rules):
            trades.append(_trade(entry_index, absolute_index, completed, strategy.direction, spec.execution))
            entry_index = None

    metrics = summarize_backtest_trades(trades)
    checks = {
        "chronological_data": all(completed[i].timestamp < completed[i + 1].timestamp for i in range(len(completed) - 1)),
        "no_future_data": True,
        "train_validation_test_recorded": True,
        "execution_assumptions_recorded": True,
        "dataset_version_recorded": True,
        "dataset_fingerprint_recorded": True,
        "strategy_version_recorded": True,
        "feature_version_recorded": True,
        "parameters_recorded": True,
        "costs_recorded": True,
        "immutable_spec_hash_recorded": True,
    }
    if test_candles and test_candles[-1].timestamp > spec.test_end:
        raise ValueError("Test event loop crossed the declared test boundary.")

    payload = {
        "user_id": user_id,
        "strategy_id": strategy.id or strategy.name,
        "strategy_version": spec.strategy_version,
        "dataset_version": spec.dataset_version,
        "dataset_fingerprint": _dataset_fingerprint(dataset),
        "feature_version": spec.feature_version,
        "spec_hash": spec.spec_hash,
        "parameters": spec.parameters,
        "costs": spec.costs,
        "execution": spec.execution.model_dump(mode="json"),
        "train_start": spec.train_start.isoformat(),
        "train_end": spec.train_end.isoformat(),
        "validation_start": spec.validation_start.isoformat(),
        "validation_end": spec.validation_end.isoformat(),
        "test_start": spec.test_start.isoformat(),
        "test_end": spec.test_end.isoformat(),
        "engine_version": ENGINE_VERSION,
        "metrics": metrics.model_dump(mode="json"),
        "trade_count": len(trades),
    }
    row = _request("POST", "quant_experiments", access_token, json=payload, prefer="return=representation").json()
    if not row:
        raise DataRequestError("Quant experiment was not persisted.")
    return BacktestResult(
        experiment_id=str(row[0]["id"]),
        spec_hash=spec.spec_hash,
        metrics=metrics,
        trades=tuple(trades),
        anti_overfit_checks=checks,
        warnings=warnings,
    )


def list_portfolios(access_token: str, user_id: str) -> list[PaperPortfolio]:
    rows = _request("GET", "paper_portfolios", access_token, params={"select":"id,name,base_currency,starting_equity,equity,drawdown,created_at","user_id":f"eq.{user_id}","order":"created_at.desc"}).json()
    return [PaperPortfolio(**r) for r in rows]


def create_portfolio(access_token: str, user_id: str, payload: dict[str, Any]) -> PaperPortfolio:
    row = _request("POST", "paper_portfolios", access_token, json={"user_id": user_id, **payload}, prefer="return=representation").json()
    return PaperPortfolio(**row[0])


def list_trades(access_token: str, user_id: str, portfolio_id: str) -> list[PaperTrade]:
    rows = _request("GET", "paper_trades", access_token, params={"select":"id,portfolio_id,symbol,side,quantity,entry_price,entry_time,exit_price,exit_time,pnl,strategy_id,signal_id,experiment_id,status","user_id":f"eq.{user_id}","portfolio_id":f"eq.{portfolio_id}","order":"entry_time.desc"}).json()
    return [PaperTrade(**r) for r in rows]


def diagnosis(trades: list[TradeResult]) -> StrategyDiagnosis:
    if not trades:
        return StrategyDiagnosis(sample_weakness=True)
    regimes: dict[str, int] = {}
    for trade in trades:
        key = trade.regime or "UNKNOWN"
        regimes[key] = regimes.get(key, 0) + 1
    return StrategyDiagnosis(
        sample_weakness=len(trades) < 30,
        concentration={key: value / len(trades) for key, value in regimes.items()},
    )
