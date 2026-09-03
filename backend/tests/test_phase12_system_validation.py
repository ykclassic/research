from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import inf, nan

import pytest

from app.models.execution import ExecutionAuthorization, ExecutionMode, OrderStatus
from app.models.market import Candle, OHLCVDataset
from app.models.risk import RiskQualificationStatus
from app.models.strategy import SignalDirection
from app.models.trade_lifecycle import ExitReason, TradeLifecycleStatus, trade_from_execution
from app.services.execution import build_order_request, execute_order
from app.services.performance import close_trade, summarize_performance
from app.services.risk_management import qualify_position
from tests.test_risk_management import make_dataset, make_features, make_selection

UTC = timezone.utc
BASE = datetime(2026, 9, 3, tzinfo=UTC)


def test_market_dataset_rejects_duplicate_timestamps() -> None:
    candle = Candle(
        timestamp=BASE,
        open=100,
        high=101,
        low=99,
        close=100,
        volume=10,
        symbol="BTC/USD",
        timeframe="1h",
        source="test",
        is_complete=True,
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        OHLCVDataset(
            symbol="BTC/USD",
            timeframe="1h",
            source="test",
            requested_at=BASE,
            candles=(candle, candle),
        )


def test_market_dataset_rejects_mixed_candle_identity() -> None:
    first = Candle(
        timestamp=BASE,
        open=100,
        high=101,
        low=99,
        close=100,
        volume=10,
        symbol="BTC/USD",
        timeframe="1h",
        source="test",
        is_complete=True,
    )
    second = first.model_copy(update={"timestamp": BASE + timedelta(hours=1), "symbol": "ETH/USD"})
    with pytest.raises(ValueError, match="dataset identity"):
        OHLCVDataset(
            symbol="BTC/USD",
            timeframe="1h",
            source="test",
            requested_at=BASE,
            candles=(first, second),
        )


def test_market_dataset_separates_completed_from_forming_candle() -> None:
    dataset = make_dataset()
    forming = dataset.candles[-1].model_copy(update={"is_complete": False})
    dataset = dataset.model_copy(update={"candles": dataset.candles[:-1] + (forming,)})
    assert len(dataset.completed_candles) == len(dataset.candles) - 1
    assert dataset.latest_candle.is_complete is False


def test_risk_engine_fails_closed_for_non_finite_equity() -> None:
    for equity in (nan, inf, -inf):
        with pytest.raises((ValueError, TypeError)):
            qualify_position(make_selection(), make_dataset(), make_features(), equity)


def test_risk_engine_preserves_selected_direction_and_risk_controls() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    assert position.status is RiskQualificationStatus.QUALIFIED
    assert position.strategy_selection.selected_direction is SignalDirection.LONG
    assert position.risk_amount == pytest.approx(75.0)
    assert position.stop_loss < position.entry_price < position.take_profit
    assert position.reward_risk >= position.risk_policy.minimum_reward_risk


def test_risk_engine_short_position_has_directionally_valid_controls() -> None:
    position = qualify_position(
        make_selection(SignalDirection.SHORT),
        make_dataset(),
        make_features(),
        10_000,
    )
    assert position.stop_loss > position.entry_price > position.take_profit


@pytest.mark.asyncio
async def test_end_to_end_qualified_paper_trade_reaches_performance() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    order = build_order_request(position, ExecutionMode.PAPER, "phase12-e2e")
    authorization = ExecutionAuthorization(
        approved=True,
        approval_id="approval-phase12",
        approved_at=BASE,
        expires_at=BASE + timedelta(hours=1),
    )
    execution = await execute_order(order, authorization)
    assert execution.status is OrderStatus.FILLED
    trade = trade_from_execution(execution)
    assert trade.status is TradeLifecycleStatus.OPEN

    closed = close_trade(
        trade,
        position.take_profit,
        BASE + timedelta(hours=2),
        ExitReason.TAKE_PROFIT,
    )
    summary = summarize_performance([closed])[0]
    assert closed.status is TradeLifecycleStatus.CLOSED
    assert summary.closed_trade_count == 1
    assert summary.wins == 1
    assert summary.total_pnl is not None
    assert summary.average_r == pytest.approx(position.risk_policy.minimum_reward_risk)


@pytest.mark.asyncio
async def test_unqualified_position_cannot_cross_execution_boundary() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    rejected = position.model_copy(update={"status": RiskQualificationStatus.REJECTED})
    with pytest.raises(ValueError, match="QUALIFIED"):
        build_order_request(rejected, ExecutionMode.PAPER)


@pytest.mark.asyncio
async def test_unauthorized_order_never_reaches_broker() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    order = build_order_request(position, ExecutionMode.PAPER, "phase12-auth")
    result = await execute_order(order, ExecutionAuthorization())
    assert result.status is OrderStatus.REJECTED
    assert result.broker_order_id is None


@pytest.mark.asyncio
async def test_expired_authorization_never_reaches_broker() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    order = build_order_request(position, ExecutionMode.PAPER, "phase12-expired")
    authorization = ExecutionAuthorization(
        approved=True,
        approval_id="approval-expired",
        approved_at=BASE - timedelta(hours=2),
        expires_at=BASE - timedelta(hours=1),
    )
    result = await execute_order(order, authorization)
    assert result.status is OrderStatus.REJECTED
    assert result.broker_order_id is None


@pytest.mark.asyncio
async def test_research_only_order_never_reaches_broker() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    order = build_order_request(position, ExecutionMode.RESEARCH_ONLY, "phase12-research")
    authorization = ExecutionAuthorization(
        approved=True,
        approval_id="approval-research",
        approved_at=BASE,
    )
    result = await execute_order(order, authorization)
    assert result.status is OrderStatus.REJECTED
    assert result.broker_order_id is None


@pytest.mark.asyncio
async def test_live_order_is_fail_closed_without_live_adapter() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    order = build_order_request(position, ExecutionMode.LIVE, "phase12-live")
    authorization = ExecutionAuthorization(
        approved=True,
        approval_id="approval-live",
        approved_at=BASE,
    )
    result = await execute_order(order, authorization)
    assert result.status is OrderStatus.REJECTED
    assert result.broker_order_id is None


def test_trade_lifecycle_rejects_double_close() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    order = build_order_request(position, ExecutionMode.PAPER, "phase12-close")
    import asyncio

    authorization = ExecutionAuthorization(
        approved=True,
        approval_id="approval-close",
        approved_at=BASE,
    )
    execution = asyncio.run(execute_order(order, authorization))
    trade = trade_from_execution(execution)
    closed = close_trade(trade, position.take_profit, BASE + timedelta(hours=1), ExitReason.TAKE_PROFIT)
    with pytest.raises(ValueError, match="OPEN"):
        close_trade(closed, position.take_profit, BASE + timedelta(hours=2), ExitReason.MANUAL)


def test_performance_summary_is_deterministic() -> None:
    first = trade_from_execution(
        __import__("tests.test_trade_lifecycle", fromlist=["execution"]).execution()
    )
    second = close_trade(first, 110.0, BASE + timedelta(hours=1), ExitReason.TAKE_PROFIT)
    left = summarize_performance([second])
    right = summarize_performance([second])
    assert left == right


def test_trade_pnl_and_r_are_consistent() -> None:
    trade = trade_from_execution(
        __import__("tests.test_trade_lifecycle", fromlist=["execution"]).execution()
    )
    closed = close_trade(trade, 110.0, BASE + timedelta(hours=1), ExitReason.TAKE_PROFIT)
    risk_cash = abs(trade.entry_price - trade.stop_loss) * trade.quantity
    assert closed.realized_pnl == pytest.approx(closed.r_multiple * risk_cash)


def test_performance_excludes_open_trades_from_expectancy() -> None:
    trade = trade_from_execution(
        __import__("tests.test_trade_lifecycle", fromlist=["execution"]).execution()
    )
    summary = summarize_performance([trade])[0]
    assert summary.closed_trade_count == 0
    assert summary.win_rate == 0
    assert summary.average_r == 0
    assert summary.expectancy_r == 0


def test_order_request_cannot_have_non_positive_quantity() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    with pytest.raises(ValueError):
        build_order_request(
            position.model_copy(update={"position_size": 0}),
            ExecutionMode.PAPER,
        )


def test_canonical_dataset_output_is_reproducible() -> None:
    left = make_dataset()
    right = make_dataset()
    assert left == right
    assert left.completed_candles == right.completed_candles


def test_market_model_rejects_non_finite_ohlcv() -> None:
    with pytest.raises(ValueError, match="finite"):
        Candle(
            timestamp=BASE,
            open=100,
            high=101,
            low=99,
            close=nan,
            volume=10,
            symbol="BTC/USD",
            timeframe="1h",
            source="test",
            is_complete=True,
        )


def test_causal_snapshot_rule_is_explicit_for_forming_candles() -> None:
    dataset = make_dataset()
    latest = dataset.latest_candle
    assert latest.timestamp <= dataset.requested_at
    assert all(c.timestamp <= latest.timestamp for c in dataset.candles)
    assert all(c.is_complete for c in dataset.completed_candles)
