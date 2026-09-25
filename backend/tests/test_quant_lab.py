from datetime import datetime, timezone, timedelta

import pytest

from app.models.quant_lab import ExperimentSpec, ExecutionAssumptions
from app.services.quant_lab import validate_experiment


def _spec(**overrides):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = dict(
        dataset_version="dataset-v1",
        strategy_version="strategy-v1",
        feature_version="features-v1",
        train_start=now,
        train_end=now + timedelta(days=10),
        validation_start=now + timedelta(days=11),
        validation_end=now + timedelta(days=20),
        test_start=now + timedelta(days=21),
        test_end=now + timedelta(days=30),
    )
    values.update(overrides)
    return ExperimentSpec(**values)


def test_experiment_rejects_non_chronological_splits():
    spec = _spec(
        validation_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    valid, warnings = validate_experiment(spec)
    assert not valid
    assert warnings


def test_experiment_contract_is_immutable_and_hashable():
    spec = _spec(execution=ExecutionAssumptions(commission_bps=2, slippage_bps=3, spread_bps=1))
    assert len(spec.spec_hash) == 64
    with pytest.raises(TypeError):
        spec.dataset_version = "changed"


def test_experiment_hash_changes_when_execution_assumptions_change():
    base = _spec()
    changed = _spec(execution=ExecutionAssumptions(slippage_bps=5))
    assert base.spec_hash != changed.spec_hash
