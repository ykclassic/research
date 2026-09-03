from datetime import datetime, timedelta, timezone

import pytest

from app.models.execution import ExecutionResult, ExecutionMode, OrderStatus
from app.models.strategy import SignalDirection
from app.models.trade_lifecycle import ExitReason, TradeLifecycleStatus, trade_from_execution
from app.services.performance import close_trade, summarize_performance

BASE = datetime(2026, 9, 3, tzinfo=timezone.utc)


def execution(direction=SignalDirection.LONG, client="client-1", price=100.0):
    return ExecutionResult(
        client_order_id=client,
        broker_order_id=f"broker-{client}",
        symbol="BTC/USD",
        direction=direction,
        status=OrderStatus.FILLED,
        execution_mode=ExecutionMode.PAPER,
        requested_quantity=2.0,
        filled_quantity=2.0,
        requested_entry_price=price,
        fill_price=price,
        stop_loss=95.0 if direction == SignalDirection.LONG else 105.0,
        take_profit=110.0 if direction == SignalDirection.LONG else 90.0,
        strategy_id="trend_following",
        generated_at=BASE,
        executed_at=BASE,
        message="filled",
    )


def test_filled_execution_creates_open_trade() -> None:
    trade = trade_from_execution(execution())
    assert trade.status is TradeLifecycleStatus.OPEN
    assert trade.quantity == 2.0
    assert trade.entry_price == 100.0


def test_unfilled_execution_cannot_enter_lifecycle() -> None:
    item = execution()
    item = item.model_copy(update={"status": OrderStatus.REJECTED, "broker_order_id": None})
    with pytest.raises(ValueError, match="filled executions"):
        trade_from_execution(item)


def test_long_trade_closes_with_positive_r() -> None:
    trade = trade_from_execution(execution())
    closed = close_trade(trade, 110.0, BASE + timedelta(hours=1), ExitReason.TAKE_PROFIT)
    assert closed.status is TradeLifecycleStatus.CLOSED
    assert closed.realized_pnl == pytest.approx(20.0)
    assert closed.r_multiple == pytest.approx(2.0)


def test_short_trade_pnl_is_directionally_correct() -> None:
    trade = trade_from_execution(execution(SignalDirection.SHORT, "client-2"))
    closed = close_trade(trade, 90.0, BASE + timedelta(hours=1), ExitReason.TAKE_PROFIT)
    assert closed.realized_pnl == pytest.approx(20.0)
    assert closed.r_multiple == pytest.approx(2.0)


def test_performance_summary_groups_by_symbol_and_strategy() -> None:
    first = close_trade(trade_from_execution(execution()), 110.0, BASE + timedelta(hours=1), ExitReason.TAKE_PROFIT)
    second = close_trade(trade_from_execution(execution(client="client-2")), 95.0, BASE + timedelta(hours=2), ExitReason.STOP_LOSS)
    summaries = summarize_performance([first, second])
    summary = summaries[0]
    assert summary.trade_count == 2
    assert summary.closed_trade_count == 2
    assert summary.wins == 1
    assert summary.losses == 1
    assert summary.win_rate == pytest.approx(0.5)
    assert summary.total_pnl == pytest.approx(10.0)
    assert summary.average_r == pytest.approx(0.5)
    assert summary.expectancy_r == pytest.approx(0.5)
    assert summary.profit_factor == pytest.approx(2.0)


def test_open_trade_is_excluded_from_closed_performance() -> None:
    open_trade = trade_from_execution(execution())
    summary = summarize_performance([open_trade])[0]
    assert summary.trade_count == 1
    assert summary.closed_trade_count == 0
    assert summary.total_pnl == 0
