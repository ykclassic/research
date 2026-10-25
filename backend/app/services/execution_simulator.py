"""Deterministic exchange simulator for execution lifecycle development.

This module is isolated from the live execution route. It has no network client,
exchange credentials, or live-capable adapter. It models idempotency, ambiguous
submission outcomes, and reconciliation before a real provider adapter exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Mapping


class SimulatedOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    TIMEOUT_BEFORE_SUBMIT = "TIMEOUT_BEFORE_SUBMIT"
    TIMEOUT_AFTER_SUBMIT = "TIMEOUT_AFTER_SUBMIT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class SimulationError(RuntimeError):
    """Base error for deterministic simulation failures."""


class SubmissionOutcomeUnknown(SimulationError):
    """The provider may have accepted the order; reconcile before retrying."""


class SubmissionRejected(SimulationError):
    """The simulated venue explicitly rejected the order."""


class ProviderUnavailable(SimulationError):
    """The simulated venue is unavailable before accepting a request."""


@dataclass(frozen=True)
class SimulatedOrder:
    client_order_id: str
    idempotency_key: str
    symbol: str
    side: str
    quantity: float
    limit_price: float

    def __post_init__(self) -> None:
        if not self.client_order_id.strip() or not self.idempotency_key.strip():
            raise ValueError("Order and idempotency identifiers are required.")
        if not self.symbol.strip() or self.side not in {"BUY", "SELL"}:
            raise ValueError("A symbol and BUY/SELL side are required.")
        if self.quantity <= 0 or self.limit_price <= 0:
            raise ValueError("Quantity and limit price must be positive.")


@dataclass(frozen=True)
class SimulatedOrderState:
    client_order_id: str
    provider_order_id: str
    status: str
    requested_quantity: float
    filled_quantity: float
    average_fill_price: float | None
    outcome: str


@dataclass(frozen=True)
class SimulationReceipt:
    status: str
    client_order_id: str
    provider_order_id: str | None
    filled_quantity: float
    average_fill_price: float | None
    reason_code: str | None = None


class SimulatedExchangeAdapter:
    """In-memory venue with deterministic outcomes and client-ID lookup."""

    def __init__(
        self,
        outcomes: Mapping[str, SimulatedOutcome] | None = None,
        fill_price: float | None = None,
    ) -> None:
        self._outcomes = dict(outcomes or {})
        self._fill_price = fill_price
        self._orders: dict[str, SimulatedOrderState] = {}
        self.submission_count: dict[str, int] = {}

    @staticmethod
    def _provider_id(client_order_id: str) -> str:
        digest = sha256(client_order_id.encode("utf-8")).hexdigest()[:20]
        return f"SIM-{digest}"

    def submit(self, order: SimulatedOrder) -> SimulatedOrderState:
        """Submit once per client ID; ambiguous outcomes are never auto-retried."""
        existing = self._orders.get(order.client_order_id)
        if existing is not None:
            return existing
        self.submission_count[order.client_order_id] = (
            self.submission_count.get(order.client_order_id, 0) + 1
        )

        outcome = self._outcomes.get(order.client_order_id, SimulatedOutcome.FILLED)
        if outcome == SimulatedOutcome.PROVIDER_UNAVAILABLE:
            raise ProviderUnavailable("SIMULATED_PROVIDER_UNAVAILABLE")
        if outcome == SimulatedOutcome.TIMEOUT_BEFORE_SUBMIT:
            raise ProviderUnavailable("SIMULATED_TIMEOUT_BEFORE_SUBMIT")
        if outcome == SimulatedOutcome.REJECTED:
            raise SubmissionRejected("SIMULATED_ORDER_REJECTED")

        provider_id = self._provider_id(order.client_order_id)
        if outcome == SimulatedOutcome.TIMEOUT_AFTER_SUBMIT:
            self._orders[order.client_order_id] = SimulatedOrderState(
                order.client_order_id, provider_id, "ACCEPTED",
                order.quantity, 0.0, None, outcome.value,
            )
            raise SubmissionOutcomeUnknown("SIMULATED_SUBMISSION_OUTCOME_UNKNOWN")

        if outcome == SimulatedOutcome.ACCEPTED:
            state = SimulatedOrderState(
                order.client_order_id, provider_id, "ACCEPTED",
                order.quantity, 0.0, None, outcome.value,
            )
        elif outcome == SimulatedOutcome.PARTIAL_FILL:
            state = SimulatedOrderState(
                order.client_order_id, provider_id, "PARTIALLY_FILLED",
                order.quantity, order.quantity / 2.0,
                self._fill_price or order.limit_price, outcome.value,
            )
        else:
            state = SimulatedOrderState(
                order.client_order_id, provider_id, "FILLED",
                order.quantity, order.quantity,
                self._fill_price or order.limit_price, outcome.value,
            )
        self._orders[order.client_order_id] = state
        return state

    def lookup_by_client_order_id(self, client_order_id: str) -> SimulatedOrderState | None:
        """Read-only provider lookup used to reconcile ambiguous outcomes."""
        return self._orders.get(client_order_id)


class SimulatedExecutionOrchestrator:
    """Approval-gated simulator with idempotency semantics.

    The in-memory ledger is for deterministic tests only; it is not production
    persistence. The production order endpoint remains fail-closed.
    """

    def __init__(self, adapter: SimulatedExchangeAdapter) -> None:
        self.adapter = adapter
        self._idempotency: dict[str, tuple[str, SimulationReceipt]] = {}

    def submit(
        self,
        order: SimulatedOrder,
        *,
        approval_valid: bool,
        risk_revalidated: bool,
        mode: str = "SIMULATION",
    ) -> SimulationReceipt:
        fingerprint = sha256(
            "|".join((
                order.client_order_id, order.symbol, order.side,
                format(order.quantity, ".12g"), format(order.limit_price, ".12g"),
            )).encode("utf-8")
        ).hexdigest()
        prior = self._idempotency.get(order.idempotency_key)
        if prior:
            if prior[0] != fingerprint:
                raise SimulationError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_ORDER")
            return prior[1]
        if mode != "SIMULATION":
            return SimulationReceipt(
                "BLOCKED", order.client_order_id, None, 0.0, None,
                "LIVE_SUBMISSION_DISABLED",
            )
        if not approval_valid:
            return SimulationReceipt(
                "BLOCKED", order.client_order_id, None, 0.0, None,
                "APPROVAL_INVALID",
            )
        if not risk_revalidated:
            return SimulationReceipt(
                "BLOCKED", order.client_order_id, None, 0.0, None,
                "RISK_REVALIDATION_FAILED",
            )

        try:
            state = self.adapter.submit(order)
        except SubmissionOutcomeUnknown:
            receipt = SimulationReceipt(
                "UNKNOWN_RECONCILIATION_REQUIRED", order.client_order_id,
                None, 0.0, None, "SUBMISSION_OUTCOME_UNKNOWN",
            )
        except SubmissionRejected:
            receipt = SimulationReceipt(
                "REJECTED", order.client_order_id, None, 0.0, None,
                "VENUE_REJECTED",
            )
        except ProviderUnavailable as exc:
            code = str(exc) if str(exc) in {
                "SIMULATED_PROVIDER_UNAVAILABLE", "SIMULATED_TIMEOUT_BEFORE_SUBMIT"
            } else "SIMULATED_PROVIDER_UNAVAILABLE"
            receipt = SimulationReceipt(
                "NOT_SUBMITTED", order.client_order_id, None, 0.0, None, code,
            )
        else:
            receipt = SimulationReceipt(
                state.status, state.client_order_id, state.provider_order_id,
                state.filled_quantity, state.average_fill_price,
            )
        self._idempotency[order.idempotency_key] = (fingerprint, receipt)
        return receipt

    def reconcile(self, order: SimulatedOrder) -> SimulationReceipt:
        """Resolve an ambiguous result via provider lookup; never resubmit."""
        prior = self._idempotency.get(order.idempotency_key)
        if prior is None:
            raise SimulationError("NO_PRIOR_SUBMISSION_TO_RECONCILE")
        state = self.adapter.lookup_by_client_order_id(order.client_order_id)
        if state is None:
            return SimulationReceipt(
                "UNKNOWN_RECONCILIATION_REQUIRED", order.client_order_id,
                None, 0.0, None, "PROVIDER_ORDER_NOT_YET_VISIBLE",
            )
        receipt = SimulationReceipt(
            state.status, state.client_order_id, state.provider_order_id,
            state.filled_quantity, state.average_fill_price,
        )
        self._idempotency[order.idempotency_key] = (prior[0], receipt)
        return receipt
