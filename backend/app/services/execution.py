from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Protocol

from app.models.execution import ExecutionAuthorization, ExecutionMode, ExecutionResult, OrderRequest, OrderStatus
from app.models.risk import PositionQualification, RiskQualificationStatus
from app.models.strategy import SignalDirection


class BrokerAdapter(Protocol):
    name: str
    supports_live: bool

    async def submit_order(self, order: OrderRequest) -> tuple[str, float]:
        """Submit an order and return broker order id and fill price."""


class PaperBrokerAdapter:
    name = "paper"
    supports_live = False

    async def submit_order(self, order: OrderRequest) -> tuple[str, float]:
        digest = sha256(order.client_order_id.encode("utf-8")).hexdigest()[:16]
        return f"PAPER-{digest}", order.entry_price


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _client_order_id(position: PositionQualification) -> str:
    seed = "|".join(
        (
            position.symbol,
            position.strategy_selection.selected_strategy_id or "",
            position.generated_at.isoformat(),
            f"{position.entry_price:.12g}",
            f"{position.position_size:.12g}",
        )
    )
    return f"RES-{sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def build_order_request(
    position: PositionQualification,
    execution_mode: ExecutionMode,
    client_order_id: str | None = None,
) -> OrderRequest:
    if position.status != RiskQualificationStatus.QUALIFIED:
        raise ValueError("Only a QUALIFIED position may be converted into an order.")
    direction = position.strategy_selection.selected_direction
    if direction not in {SignalDirection.LONG, SignalDirection.SHORT}:
        raise ValueError("Execution requires a directional strategy selection.")
    return OrderRequest(
        client_order_id=client_order_id or _client_order_id(position),
        symbol=position.symbol,
        direction=direction,
        quantity=position.position_size,
        entry_price=position.entry_price,
        stop_loss=position.stop_loss,
        take_profit=position.take_profit,
        strategy_id=position.strategy_selection.selected_strategy_id or "unknown",
        risk_policy_version=position.risk_policy.policy_version,
        execution_mode=execution_mode,
        created_at=_utcnow(),
    )


def _authorization_valid(authorization: ExecutionAuthorization, now: datetime) -> bool:
    if not authorization.approved or not authorization.approval_id or not authorization.approved_at:
        return False
    if authorization.approved_at > now:
        return False
    return authorization.expires_at is None or now <= authorization.expires_at


async def execute_order(
    order: OrderRequest,
    authorization: ExecutionAuthorization,
    broker: BrokerAdapter | None = None,
) -> ExecutionResult:
    now = _utcnow()
    if order.execution_mode == ExecutionMode.RESEARCH_ONLY:
        return ExecutionResult(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            direction=order.direction,
            status=OrderStatus.REJECTED,
            execution_mode=order.execution_mode,
            requested_quantity=order.quantity,
            requested_entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            strategy_id=order.strategy_id,
            generated_at=order.created_at,
            message="Research-only mode cannot submit orders.",
        )

    if not _authorization_valid(authorization, now):
        return ExecutionResult(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            direction=order.direction,
            status=OrderStatus.REJECTED,
            execution_mode=order.execution_mode,
            requested_quantity=order.quantity,
            requested_entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            strategy_id=order.strategy_id,
            generated_at=order.created_at,
            message="Explicit, valid human execution authorization is required.",
        )

    adapter = broker or PaperBrokerAdapter()
    if order.execution_mode == ExecutionMode.LIVE and not adapter.supports_live:
        return ExecutionResult(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            direction=order.direction,
            status=OrderStatus.REJECTED,
            execution_mode=order.execution_mode,
            requested_quantity=order.quantity,
            requested_entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            strategy_id=order.strategy_id,
            generated_at=order.created_at,
            message=f"Broker adapter '{adapter.name}' does not support live execution.",
        )

    try:
        broker_order_id, fill_price = await adapter.submit_order(order)
    except Exception as exc:
        return ExecutionResult(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            direction=order.direction,
            status=OrderStatus.FAILED,
            execution_mode=order.execution_mode,
            requested_quantity=order.quantity,
            requested_entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            strategy_id=order.strategy_id,
            generated_at=order.created_at,
            message=f"Broker submission failed: {exc}",
        )

    return ExecutionResult(
        client_order_id=order.client_order_id,
        broker_order_id=broker_order_id,
        symbol=order.symbol,
        direction=order.direction,
        status=OrderStatus.FILLED,
        execution_mode=order.execution_mode,
        requested_quantity=order.quantity,
        filled_quantity=order.quantity,
        requested_entry_price=order.entry_price,
        fill_price=fill_price,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
        strategy_id=order.strategy_id,
        generated_at=order.created_at,
        executed_at=now,
        message=f"Order filled by {adapter.name} adapter.",
    )
