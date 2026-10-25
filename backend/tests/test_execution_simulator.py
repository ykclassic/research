from __future__ import annotations

import pytest

from app.services.execution_simulator import (
    SimulatedExecutionOrchestrator,
    SimulatedExchangeAdapter,
    SimulatedOrder,
    SimulatedOutcome,
    SimulationError,
)


def make_order(**overrides) -> SimulatedOrder:
    values = {
        "client_order_id": "client-1",
        "idempotency_key": "idem-1",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "quantity": 0.02,
        "limit_price": 65000.0,
    }
    values.update(overrides)
    return SimulatedOrder(**values)


def test_simulator_blocks_missing_approval_or_failed_risk() -> None:
    adapter = SimulatedExchangeAdapter()
    orchestrator = SimulatedExecutionOrchestrator(adapter)
    first = orchestrator.submit(make_order(), approval_valid=False, risk_revalidated=True)
    assert first.status == "BLOCKED"
    assert first.reason_code == "APPROVAL_INVALID"
    assert adapter.submission_count == {}

    second = orchestrator.submit(
        make_order(client_order_id="client-2", idempotency_key="idem-2"),
        approval_valid=True, risk_revalidated=False,
    )
    assert second.reason_code == "RISK_REVALIDATION_FAILED"
    assert adapter.submission_count == {}


def test_non_simulation_mode_is_always_blocked() -> None:
    adapter = SimulatedExchangeAdapter()
    receipt = SimulatedExecutionOrchestrator(adapter).submit(
        make_order(), approval_valid=True, risk_revalidated=True, mode="LIVE"
    )
    assert receipt.status == "BLOCKED"
    assert receipt.reason_code == "LIVE_SUBMISSION_DISABLED"
    assert adapter.submission_count == {}


def test_duplicate_idempotency_key_returns_same_receipt_without_resubmit() -> None:
    order = make_order()
    adapter = SimulatedExchangeAdapter()
    orchestrator = SimulatedExecutionOrchestrator(adapter)
    first = orchestrator.submit(order, approval_valid=True, risk_revalidated=True)
    second = orchestrator.submit(order, approval_valid=True, risk_revalidated=True)
    assert first == second
    assert adapter.submission_count[order.client_order_id] == 1


def test_idempotency_key_cannot_be_reused_for_changed_order() -> None:
    orchestrator = SimulatedExecutionOrchestrator(SimulatedExchangeAdapter())
    orchestrator.submit(make_order(), approval_valid=True, risk_revalidated=True)
    with pytest.raises(SimulationError, match="IDEMPOTENCY_KEY_REUSED"):
        orchestrator.submit(
            make_order(quantity=0.03), approval_valid=True, risk_revalidated=True
        )


def test_ambiguous_submission_is_not_retried_and_can_be_reconciled() -> None:
    order = make_order()
    adapter = SimulatedExchangeAdapter({
        order.client_order_id: SimulatedOutcome.TIMEOUT_AFTER_SUBMIT
    })
    orchestrator = SimulatedExecutionOrchestrator(adapter)
    first = orchestrator.submit(order, approval_valid=True, risk_revalidated=True)
    assert first.status == "UNKNOWN_RECONCILIATION_REQUIRED"
    assert orchestrator.submit(order, approval_valid=True, risk_revalidated=True) == first
    assert adapter.submission_count[order.client_order_id] == 1

    reconciled = orchestrator.reconcile(order)
    assert reconciled.status == "ACCEPTED"
    assert reconciled.provider_order_id is not None
    assert adapter.submission_count[order.client_order_id] == 1


def test_timeout_before_submit_is_not_retried_automatically() -> None:
    order = make_order()
    adapter = SimulatedExchangeAdapter({
        order.client_order_id: SimulatedOutcome.TIMEOUT_BEFORE_SUBMIT
    })
    receipt = SimulatedExecutionOrchestrator(adapter).submit(
        order, approval_valid=True, risk_revalidated=True
    )
    assert receipt.status == "NOT_SUBMITTED"
    assert receipt.reason_code == "SIMULATED_TIMEOUT_BEFORE_SUBMIT"
    assert adapter.submission_count[order.client_order_id] == 1


def test_partial_fill_is_preserved_for_reconciliation() -> None:
    order = make_order()
    adapter = SimulatedExchangeAdapter({
        order.client_order_id: SimulatedOutcome.PARTIAL_FILL
    })
    receipt = SimulatedExecutionOrchestrator(adapter).submit(
        order, approval_valid=True, risk_revalidated=True
    )
    assert receipt.status == "PARTIALLY_FILLED"
    assert receipt.filled_quantity == pytest.approx(order.quantity / 2)
    assert receipt.average_fill_price == order.limit_price


def test_provider_unavailable_fails_without_fake_order_id() -> None:
    order = make_order()
    adapter = SimulatedExchangeAdapter({
        order.client_order_id: SimulatedOutcome.PROVIDER_UNAVAILABLE
    })
    receipt = SimulatedExecutionOrchestrator(adapter).submit(
        order, approval_valid=True, risk_revalidated=True
    )
    assert receipt.status == "NOT_SUBMITTED"
    assert receipt.provider_order_id is None
    assert receipt.reason_code == "SIMULATED_PROVIDER_UNAVAILABLE"


def test_reconciliation_requires_prior_submission() -> None:
    order = make_order()
    orchestrator = SimulatedExecutionOrchestrator(SimulatedExchangeAdapter())
    with pytest.raises(SimulationError, match="NO_PRIOR_SUBMISSION"):
        orchestrator.reconcile(order)


def test_order_validation_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        make_order(quantity=0)
    with pytest.raises(ValueError):
        make_order(side="HOLD")
