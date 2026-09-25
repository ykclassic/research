from datetime import datetime,timezone,timedelta
from app.models.quant_lab import ExperimentSpec
from app.services.quant_lab import _metrics,validate_experiment
def test_metrics_include_quant_diagnostics():
    T=type("T",(),{})
    a=T(); a.pnl=10;a.r_multiple=.1;a.regime="UP";a.timeframe="1h"
    b=T(); b.pnl=-5;b.r_multiple=-.05;b.regime="DOWN";b.timeframe="1h"
    result=_metrics([a,b]); assert result.trades==2; assert result.profit_factor==2; assert result.max_drawdown==5; assert result.win_rate==.5
def test_experiment_rejects_non_chronological_splits():
    now=datetime.now(timezone.utc)
    spec=ExperimentSpec(dataset_version="d1",strategy_version="s1",feature_version="f1",train_start=now,train_end=now+timedelta(days=1),validation_start=now+timedelta(hours=12),validation_end=now+timedelta(days=2),test_start=now+timedelta(days=3),test_end=now+timedelta(days=4))
    valid,warnings=validate_experiment(spec); assert not valid and warnings
