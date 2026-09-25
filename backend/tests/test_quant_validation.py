from datetime import datetime, timezone, timedelta

from app.models.quant_lab import (
    BacktestMetrics,
    BacktestResult,
    ExperimentSpec,
    Side,
    StrategyDefinition,
    StrategyRule,
    TradeResult,
)
from app.services.quant_validation import monte_carlo, parameter_sensitivity, robustness, validate_strategy_definition


def spec():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ExperimentSpec(
        dataset_version="d1",
        strategy_version="s1",
        feature_version="f1",
        train_start=now,
        train_end=now + timedelta(days=10),
        validation_start=now + timedelta(days=11),
        validation_end=now + timedelta(days=20),
        test_start=now + timedelta(days=21),
        test_end=now + timedelta(days=30),
    )


def result():
    trades = tuple(
        TradeResult(
            entry_time=datetime(2026, 1, 22, tzinfo=timezone.utc),
            exit_time=datetime(2026, 1, 23, tzinfo=timezone.utc),
            side=Side.LONG,
            entry_price=100,
            exit_price=102 if i % 2 == 0 else 99,
            pnl=2 if i % 2 == 0 else -1,
            r_multiple=2 if i % 2 == 0 else -1,
            mae=-1,
            mfe=3,
            timeframe="H1",
        )
        for i in range(40)
    )
    metrics = BacktestMetrics(
        trades=40,
        net_pnl=20,
        expectancy=.5,
        profit_factor=4 / 1,
        win_rate=.5,
        max_drawdown=2,
        average_r=.5,
        r_distribution=tuple(t.r_multiple for t in trades),
    )
    return BacktestResult(experiment_id="e1", spec_hash=spec().spec_hash, metrics=metrics, trades=trades, anti_overfit_checks={})


def test_strategy_builder_rejects_unknown_fields():
    strategy = StrategyDefinition(
        name="test",
        entry_rules=(StrategyRule(field="regime", operator="eq", value="STRONG_TREND_UP"),),
        exit_rules=(StrategyRule(field="close", operator="lt", value=100),),
    )
    assert "Unsupported rule field: regime" in validate_strategy_definition(strategy)


def test_monte_carlo_is_deterministic():
    a = monte_carlo(result(), simulations=500, seed=11)
    b = monte_carlo(result(), simulations=500, seed=11)
    assert a == b
    assert a.simulations == 500


def test_parameter_sensitivity_is_explicit_and_reproducible():
    out = parameter_sensitivity(result(), "slippage_bps", [0, 5, 10])
    assert out.parameter == "slippage_bps"
    assert len(out.net_pnl) == 3


def test_robustness_records_sample_warning_for_small_sample():
    r = result().model_copy(update={"metrics": result().metrics.model_copy(update={"trades": 10})})
    out = robustness(r, spec(), {"slippage_bps": [0, 5, 10]})
    assert not out.scorecard["sufficient_sample"]
    assert any("Small sample" in w for w in out.warnings)
