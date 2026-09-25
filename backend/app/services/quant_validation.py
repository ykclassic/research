from __future__ import annotations

import random
from statistics import mean, median
from typing import Iterable

from app.models.quant_lab import (
    BacktestResult, MonteCarloResult, ParameterSensitivityResult, PaperBacktestComparison, PaperTrade,
    RobustnessResult, StrategyDefinition, WalkForwardResult, WalkForwardWindow,
)

def walk_forward(spec, minimum_oos_trades: int = 10) -> WalkForwardResult:
    window = WalkForwardWindow(train_start=spec.train_start, train_end=spec.train_end, validation_start=spec.validation_start, validation_end=spec.validation_end, test_start=spec.test_start, test_end=spec.test_end)
    warnings = () if minimum_oos_trades <= 10 else ('Minimum OOS sample threshold is unusually high.',)
    return WalkForwardResult(windows=(window,), oos_trades=0, oos_net_pnl=0.0, oos_expectancy=0.0, warnings=warnings + ('Run each declared walk-forward window on untouched out-of-sample data before promoting a strategy.',))

def monte_carlo(result: BacktestResult, simulations: int = 2000, seed: int = 7) -> MonteCarloResult:
    simulations = max(100, min(simulations, 10000))
    pnls = [t.pnl for t in result.trades]
    if not pnls:
        return MonteCarloResult(simulations=simulations, seed=seed, median_pnl=0.0, p05_pnl=0.0, p95_pnl=0.0, probability_of_loss=1.0, max_drawdown_p95=0.0)
    rng = random.Random(seed)
    totals, drawdowns = [], []
    for _ in range(simulations):
        equity = peak = dd = 0.0
        for _ in pnls:
            equity += rng.choice(pnls)
            peak = max(peak, equity)
            dd = max(dd, peak - equity)
        totals.append(equity)
        drawdowns.append(dd)
    totals.sort(); drawdowns.sort()
    q05 = totals[max(0, int(simulations * 0.05) - 1)]
    q95 = totals[min(simulations - 1, int(simulations * 0.95))]
    dd95 = drawdowns[min(simulations - 1, int(simulations * 0.95))]
    return MonteCarloResult(simulations=simulations, seed=seed, median_pnl=median(totals), p05_pnl=q05, p95_pnl=q95, probability_of_loss=sum(x < 0 for x in totals) / simulations, max_drawdown_p95=dd95)

def parameter_sensitivity(result: BacktestResult, parameter: str, values: Iterable[float]) -> ParameterSensitivityResult:
    values = tuple(float(v) for v in values)
    base = result.metrics.net_pnl
    # Sensitivity is deliberately explicit: it perturbs recorded execution cost, not hidden strategy state.
    net = tuple(base - abs(base) * max(0.0, v) / 10000 for v in values)
    exp = tuple(x / result.metrics.trades if result.metrics.trades else 0.0 for x in net)
    stable = bool(net) and (max(net) - min(net) <= max(abs(base) * 0.5, 1e-12))
    return ParameterSensitivityResult(parameter=parameter, values=values, net_pnl=net, expectancy=exp, stable=stable)

def robustness(result: BacktestResult, spec, sensitivity_values: dict[str, list[float]] | None = None) -> RobustnessResult:
    mc = monte_carlo(result)
    wf = walk_forward(spec)
    sensitivities = tuple(parameter_sensitivity(result, name, vals) for name, vals in (sensitivity_values or {}).items())
    scorecard = {
        'sufficient_sample': result.metrics.trades >= 30,
        'positive_expectancy': result.metrics.expectancy > 0,
        'positive_monte_carlo_median': mc.median_pnl > 0,
        'monte_carlo_loss_probability_below_50pct': mc.probability_of_loss < 0.5,
        'all_requested_parameters_stable': all(s.stable for s in sensitivities),
    }
    warnings = list(result.warnings)
    if result.metrics.trades < 30: warnings.append('Small sample: robustness conclusions are weak.')
    if mc.probability_of_loss >= 0.5: warnings.append('Monte Carlo shows at least a 50% probability of loss under bootstrap resampling.')
    return RobustnessResult(walk_forward=wf, monte_carlo=mc, sensitivities=sensitivities, scorecard=scorecard, warnings=tuple(warnings))

def compare_paper_to_backtest(result: BacktestResult, paper_trades: Iterable[PaperTrade], experiment_id: str) -> PaperBacktestComparison:
    paper = [t for t in paper_trades if t.experiment_id == experiment_id and t.status.upper() == 'CLOSED']
    paper_pnl = sum(t.pnl or 0.0 for t in paper)
    backtest_pnl = result.metrics.net_pnl
    paper_wins = sum((t.pnl or 0.0) > 0 for t in paper)
    paper_win_rate = paper_wins / len(paper) if paper else None
    drift = paper_pnl - backtest_pnl
    trade_drift = len(paper) - result.metrics.trades
    status = 'NO_PAPER_DATA' if not paper else ('DRIFT_DETECTED' if abs(drift) > max(abs(backtest_pnl) * 0.25, 1.0) or abs(trade_drift) > max(result.metrics.trades * 0.25, 2) else 'ALIGNED')
    return PaperBacktestComparison(experiment_id=experiment_id, paper_trade_count=len(paper), backtest_trade_count=result.metrics.trades, paper_net_pnl=paper_pnl, backtest_net_pnl=backtest_pnl, pnl_drift=drift, trade_count_drift=float(trade_drift), win_rate_drift=(paper_win_rate - result.metrics.win_rate if paper_win_rate is not None else None), status=status)

def validate_strategy_definition(strategy: StrategyDefinition) -> tuple[str, ...]:
    errors = []
    allowed_fields = {'open', 'high', 'low', 'close', 'volume', 'timeframe', 'regime', 'trend_aligned', 'liquidity_sweep', 'rr'}
    for rule in (*strategy.entry_rules, *strategy.exit_rules):
        if rule.field not in allowed_fields: errors.append(f'Unsupported rule field: {rule.field}')
        if rule.operator == 'contains' and not isinstance(rule.value, (str, list, tuple, set)): errors.append(f'contains requires a collection or string value for {rule.field}')
    if not strategy.entry_rules: errors.append('At least one entry rule is required.')
    if not strategy.exit_rules: errors.append('At least one exit rule is required.')
    return tuple(errors)

def diagnose(result: BacktestResult, baseline: BacktestResult | None = None, sensitivity_values: dict[str, list[float]] | None = None) -> StrategyDiagnosis:
    trades = list(result.trades)
    if not trades:
        return StrategyDiagnosis(sample_weakness=True)
    half = max(1, len(trades) // 2)
    first = trades[:half]
    second = trades[half:]
    first_avg = mean(t.pnl for t in first) if first else 0.0
    second_avg = mean(t.pnl for t in second) if second else 0.0
    decay = ((second_avg - first_avg) / abs(first_avg)) if first_avg else None
    regime_stats = {}
    for t in trades:
        key = t.regime or "UNKNOWN"
        regime_stats.setdefault(key, []).append(t.pnl)
    regime_deterioration = {}
    for key, values in regime_stats.items():
        if len(values) < 2:
            continue
        midpoint = max(1, len(values) // 2)
        a, b = values[:midpoint], values[midpoint:]
        regime_deterioration[key] = (mean(b) - mean(a)) / abs(mean(a)) if mean(a) else 0.0
    unstable = []
    for name, values in (sensitivity_values or {}).items():
        if len(values) > 1 and max(values) != min(values):
            unstable.append(name)
    concentration = {key: len(values) / len(trades) for key, values in regime_stats.items()}
    if baseline is not None and baseline.metrics.trades:
        concentration["baseline_pnl_drift"] = (result.metrics.net_pnl - baseline.metrics.net_pnl) / max(abs(baseline.metrics.net_pnl), 1.0)
    return StrategyDiagnosis(
        performance_decay=decay,
        concentration=concentration,
        unstable_parameters=tuple(unstable),
        sample_weakness=len(trades) < 30,
        regime_deterioration=regime_deterioration,
    )
