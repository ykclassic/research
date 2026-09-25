from __future__ import annotations

from collections import defaultdict

from app.models.trade_lifecycle import PerformanceSummary, TradeLifecycleStatus, TradeOutcome


def close_trade(trade: TradeOutcome, exit_price: float, exit_time, reason) -> TradeOutcome:
    if trade.status != TradeLifecycleStatus.OPEN:
        raise ValueError("Only OPEN trades can be closed.")
    if exit_price <= 0:
        raise ValueError("Exit price must be greater than zero.")
    if exit_time <= trade.entry_time:
        raise ValueError("Exit time must be after entry time.")

    price_change = exit_price - trade.entry_price
    signed_change = price_change if trade.direction.value == "LONG" else -price_change
    pnl = signed_change * trade.quantity
    risk_per_unit = abs(trade.entry_price - trade.stop_loss)
    r_multiple = signed_change / risk_per_unit
    return trade.model_copy(update={
        "exit_price": exit_price,
        "status": TradeLifecycleStatus.CLOSED,
        "exit_reason": reason,
        "realized_pnl": pnl,
        "r_multiple": r_multiple,
        "exit_time": exit_time,
    })


def summarize_performance(trades: list[TradeOutcome]) -> tuple[PerformanceSummary, ...]:
    groups: dict[tuple[str, str], list[TradeOutcome]] = defaultdict(list)
    for trade in trades:
        groups[(trade.symbol, trade.strategy_id)].append(trade)

    summaries: list[PerformanceSummary] = []
    for (symbol, strategy_id), group in sorted(groups.items()):
        closed = [t for t in group if t.status == TradeLifecycleStatus.CLOSED]
        r_values = [t.r_multiple for t in closed if t.r_multiple is not None]
        pnl_values = [t.realized_pnl for t in closed if t.realized_pnl is not None]
        wins = sum(1 for value in r_values if value > 0)
        losses = sum(1 for value in r_values if value < 0)
        gross_profit = sum(value for value in pnl_values if value > 0)
        gross_loss = -sum(value for value in pnl_values if value < 0)
        win_rate = wins / len(closed) if closed else 0.0
        average_r = sum(r_values) / len(r_values) if r_values else 0.0
        expectancy_r = average_r
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        summaries.append(PerformanceSummary(
            symbol=symbol,
            strategy_id=strategy_id,
            trade_count=len(group),
            closed_trade_count=len(closed),
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            total_pnl=sum(pnl_values),
            average_r=average_r,
            expectancy_r=expectancy_r,
            profit_factor=profit_factor,
        ))
    return tuple(summaries)


def summarize_backtest_trades(trades):
    """Canonical performance aggregation for deterministic Quant Lab results."""
    from app.models.quant_lab import BacktestMetrics

    if not trades:
        return BacktestMetrics(
            trades=0,
            net_pnl=0,
            expectancy=0,
            profit_factor=None,
            win_rate=0,
            max_drawdown=0,
            average_r=0,
        )

    pnls = [trade.pnl for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    equity = peak = max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    def breakdown(key):
        groups = {}
        for trade in trades:
            groups.setdefault(key(trade), []).append(trade)
        return {
            group: {
                "trades": float(len(items)),
                "net_pnl": sum(item.pnl for item in items),
                "win_rate": sum(item.pnl > 0 for item in items) / len(items),
            }
            for group, items in groups.items()
        }

    return BacktestMetrics(
        trades=len(trades),
        net_pnl=sum(pnls),
        expectancy=sum(pnls) / len(pnls),
        profit_factor=(sum(wins) / abs(sum(losses)) if losses else None),
        win_rate=len(wins) / len(trades),
        max_drawdown=max_drawdown,
        average_r=sum(trade.r_multiple for trade in trades) / len(trades),
        r_distribution=tuple(trade.r_multiple for trade in trades),
        regime_breakdown=breakdown(lambda trade: trade.regime or "UNKNOWN"),
        timeframe_breakdown=breakdown(lambda trade: trade.timeframe),
    )
