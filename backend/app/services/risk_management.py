from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from app.models.market import OHLCVDataset, TechnicalAnalysisResult
from app.models.risk import PositionQualification, RiskPolicy, RiskQualificationStatus
from app.models.strategy import SignalDirection
from app.models.strategy_selection import StrategySelectionResult
from app.services.trade_contract import build_trade_contract

RISK_POLICY = RiskPolicy()


def qualify_position(selection: StrategySelectionResult, dataset: OHLCVDataset, features: TechnicalAnalysisResult, account_equity: float, policy: RiskPolicy = RISK_POLICY) -> PositionQualification:
    """Produce the same deterministic trade contract used by signal generation.

    This remains non-executable: it only qualifies a candidate and records the
    exact entry/stop/target/risk assumptions used for sizing.
    """
    if selection.symbol != features.symbol or selection.symbol != dataset.symbol:
        raise ValueError("Strategy selection, dataset, and feature symbols must match.")
    completed = dataset.completed_candles
    if len(completed) < 14:
        raise ValueError("At least 14 completed candles are required for ATR risk qualification.")
    if not isfinite(account_equity) or account_equity <= 0:
        raise ValueError("account_equity must be greater than zero and finite.")
    direction = selection.selected_direction
    atr = features.indicators.get("atr14")
    entry = completed[-1].close
    if not isinstance(atr, (int, float)) or not isfinite(float(atr)) or float(atr) <= 0:
        raise ValueError("A positive finite ATR14 is required for risk qualification.")
    if not isfinite(float(entry)) or float(entry) <= 0:
        raise ValueError("A positive finite entry price is required for risk qualification.")
    direction_name = "BUY" if direction is SignalDirection.LONG else "SELL" if direction is SignalDirection.SHORT else "NEUTRAL"
    contract = build_trade_contract(direction=direction_name, entry_price=float(entry), stop_distance=float(atr) * policy.stop_atr_multiplier, target_price=float(entry) + (float(atr) * policy.stop_atr_multiplier * policy.minimum_reward_risk if direction is SignalDirection.LONG else -float(atr) * policy.stop_atr_multiplier * policy.minimum_reward_risk), account_equity=account_equity, risk_fraction=policy.risk_per_trade)
    reasons = list(contract.reasons)
    if contract.reward_risk < policy.minimum_reward_risk:
        reasons.append("Calculated reward/risk is below the minimum policy threshold.")
    status = RiskQualificationStatus.QUALIFIED if not reasons else RiskQualificationStatus.REJECTED
    if status is RiskQualificationStatus.QUALIFIED:
        reasons.append(f"Unified trade contract qualified at {policy.risk_per_trade:.2%} equity risk and {contract.reward_risk:.2f}:1 reward/risk.")
    return PositionQualification(symbol=selection.symbol, generated_at=datetime.now(timezone.utc), strategy_selection=selection, status=status, risk_policy=policy, account_equity=account_equity, risk_amount=contract.risk_amount or 0.0, entry_price=contract.entry_price, atr=float(atr), stop_distance=contract.stop_distance, stop_loss=contract.stop_loss, take_profit=contract.take_profit, position_size=contract.position_size or 0.0000001, reward_risk=contract.reward_risk, reasons=tuple(reasons))
