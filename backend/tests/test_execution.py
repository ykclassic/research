from datetime import datetime, timezone

import pytest

from app.models.execution import ExecutionAuthorization, ExecutionMode, OrderStatus
from app.models.risk import RiskQualificationStatus
from app.services.execution import PaperBrokerAdapter, build_order_request, execute_order
from app.services.risk_management import qualify_position
from tests.test_risk_management import make_dataset, make_features, make_selection

NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


def make_position():
    return qualify_position(make_selection(), make_dataset(), make_features(), 10_000)


def make_auth() -> ExecutionAuthorization:
    return ExecutionAuthorization(
        approved=True,
        approval_id="HITL-001",
        approved_at=NOW,
    )


@pytest.mark.asyncio
async def test_paper_execution_requires_explicit_authorization() -> None:
    position = make_position()
    order = build_order_request(position, ExecutionMode.PAPER)

    result = await execute_order(order, ExecutionAuthorization())

    assert result.status is OrderStatus.REJECTED
    assert "authorization" in result.message.lower()


@pytest.mark.asyncio
async def test_paper_execution_fills_risk_qualified_order() -> None:
    position = make_position()
    order = build_order_request(position, ExecutionMode.PAPER)

    result = await execute_order(order, make_auth(), PaperBrokerAdapter())

    assert result.status is OrderStatus.FILLED
    assert result.broker_order_id is not None
    assert result.filled_quantity == pytest.approx(position.position_size)
    assert result.fill_price == pytest.approx(position.entry_price)
    assert result.stop_loss == pytest.approx(position.stop_loss)
    assert result.take_profit == pytest.approx(position.take_profit)


def test_unqualified_position_cannot_become_order() -> None:
    position = make_position().model_copy(update={"status": RiskQualificationStatus.REJECTED})

    with pytest.raises(ValueError, match="QUALIFIED"):
        build_order_request(position, ExecutionMode.PAPER)


@pytest.mark.asyncio
async def test_live_execution_is_rejected_without_live_broker_adapter() -> None:
    position = make_position()
    order = build_order_request(position, ExecutionMode.LIVE)

    result = await execute_order(order, make_auth())

    assert result.status is OrderStatus.REJECTED
    assert "does not support live execution" in result.message


@pytest.mark.asyncio
async def test_research_only_mode_never_submits() -> None:
    position = make_position()
    order = build_order_request(position, ExecutionMode.RESEARCH_ONLY)

    result = await execute_order(order, make_auth())

    assert result.status is OrderStatus.REJECTED
    assert "research-only" in result.message.lower()


def test_order_request_preserves_risk_controls_and_direction() -> None:
    position = make_position()
    order = build_order_request(position, ExecutionMode.PAPER, "client-001")

    assert order.client_order_id == "client-001"
    assert order.direction == position.strategy_selection.selected_direction
    assert order.quantity == pytest.approx(position.position_size)
    assert order.entry_price == pytest.approx(position.entry_price)
    assert order.stop_loss == pytest.approx(position.stop_loss)
    assert order.take_profit == pytest.approx(position.take_profit)
    assert order.risk_policy_version == position.risk_policy.policy_version
