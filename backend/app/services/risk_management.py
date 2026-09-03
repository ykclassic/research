from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from app.models.market import OHLCVDataset, TechnicalAnalysisResult
from app.models.risk import PositionQualification, RiskPolicy, RiskQualificationStatus
from app.models.strategy import SignalDirection
from app.models.strategy_selection import StrategySelectionResult

RISK_POLICY = RiskPolicy()


def qualify_position(
    selection: StrategySelectionResult,
    dataset: OHLCVDataset,
    features: TechnicalAnalysisResult,
    account_equity: float,
    policy: RiskPolicy = RISK_POLICY,
) -> PositionQualification:
    """Convert a selected strategy into a deterministic, non-executable position candidate."""
    if selection.symbol != features.symbol or selection.symbol != dataset.symbol:
        raise ValueError("Strategy selection, dataset, and feature symbols must match.")
    completed = dataset.completed_candles
    if len(completed) < 14:
        raise ValueError("At least 14 completed candles are required for ATR risk qualification.")
    if not isfinite(account_equity) or account_equity <= 0:
        raise ValueError("account_equity must be greater than zero and finite.")

    direction = selection.selected_direction
    atr = features.indicators.get("atr14")
    entry_price = completed[-1].close
    if atr is None or not isinstance(atr, (int, float)) or not isfinite(float(atr)) or float(atr) <= 0:
        raise ValueError("A positive finite ATR14 is required for risk qualification.")
    if not isfinite(float(entry_price)) or float(entry_price) <= 0:
        raise ValueError("A positive finite entry price is required for risk qualification.")

    atr_value = float(atr)
    risk_amount = account_equity * policy.risk_per_trade
    stop_distance = atr_value * policy.stop_atr_multiplier

    if direction is SignalDirection.LONG:
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + (stop_distance * policy.minimum_reward_risk)
    elif direction is SignalDirection.SHORT:
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - (stop_distance * policy.minimum_reward_risk)
    else:
        raise ValueError("A directional strategy selection is required for position qualification.")

    position_size = risk_amount / stop_distance
    reward_risk = abs(take_profit - entry_price) / abs(entry_price - stop_loss)
    reasons: list[str] = []

    if stop_loss <= 0 or take_profit <= 0:
        reasons.append("Calculated stop-loss or take-profit is non-positive.")
    if reward_risk < policy.minimum_reward_risk:
        reasons.append("Calculated reward/risk is below the minimum policy threshold.")
    if position_size <= 0 or not isfinite(position_size):
        reasons.append("Calculated position size is invalid.")

    status = RiskQualificationStatus.QUALIFIED if not reasons else RiskQualificationStatus.REJECTED
    if status is RiskQualificationStatus.QUALIFIED:
        reasons.append(
            f"Risk qualified at {policy.risk_per_trade:.2%} equity risk, "
            f"{policy.stop_atr_multiplier:.2f}x ATR stop, and "
            f"{reward_risk:.2f}:1 reward/risk."
        )

    return PositionQualification(
        symbol=selection.symbol,
        generated_at=datetime.now(timezone.utc),
        strategy_selection=selection,
        status=status,
        risk_policy=policy,
        account_equity=account_equity,
        risk_amount=risk_amount,
        entry_price=entry_price,
        atr=atr_value,
        stop_distance=stop_distance,
        stop_loss=stop_loss,
        take_profit=take_profit,
        position_size=position_size,
        reward_risk=reward_risk,
        reasons=tuple(reasons),
    )
