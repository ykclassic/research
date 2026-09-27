from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TradeContract:
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance: float
    reward_risk: float
    risk_amount: float | None
    position_size: float | None
    expected_cost: float
    expected_slippage: float
    expected_spread: float
    valid: bool
    reasons: tuple[str, ...] = ()


def build_trade_contract(*, direction: str, entry_price: float, stop_distance: float, target_price: float, account_equity: float | None = None, risk_fraction: float = 0.0075, spread_bps: float = 0.0, slippage_bps: float = 0.0, fee_bps: float = 0.0, contract_multiplier: float = 1.0, lot_size: float = 0.0) -> TradeContract:
    reasons: list[str] = []
    if direction not in {"BUY", "SELL", "LONG", "SHORT"}:
        reasons.append("Directional trade contract is required.")
    if not all(isfinite(float(x)) and float(x) > 0 for x in (entry_price, stop_distance, target_price)):
        reasons.append("Entry, stop distance and target must be positive finite values.")
    if contract_multiplier <= 0:
        reasons.append("Contract multiplier must be positive.")
    if risk_fraction <= 0:
        reasons.append("Risk fraction must be positive.")
    buy = direction in {"BUY", "LONG"}
    stop = entry_price - stop_distance if buy else entry_price + stop_distance
    risk_per_unit = abs(entry_price - stop) * contract_multiplier
    reward = abs(target_price - entry_price)
    rr = reward / risk_per_unit if risk_per_unit > 0 else 0.0
    expected_cost = entry_price * (spread_bps + slippage_bps + fee_bps) / 10000.0
    risk_amount = account_equity * risk_fraction if account_equity is not None and account_equity > 0 else None
    position_size = risk_amount / risk_per_unit if risk_amount is not None and risk_per_unit > 0 else None
    if lot_size > 0 and position_size is not None:
        position_size = (position_size // lot_size) * lot_size
    if stop <= 0 or target_price <= 0:
        reasons.append("Calculated stop or target is non-positive.")
    if rr <= 0:
        reasons.append("Reward/risk is non-positive.")
    if position_size is not None and position_size <= 0:
        reasons.append("Calculated position size is below the instrument lot size.")
    return TradeContract(direction=direction, entry_price=entry_price, stop_loss=stop, take_profit=target_price, stop_distance=stop_distance, reward_risk=rr, risk_amount=risk_amount, position_size=position_size, expected_cost=expected_cost, expected_slippage=entry_price * slippage_bps / 10000.0, expected_spread=entry_price * spread_bps / 10000.0, valid=not reasons, reasons=tuple(reasons))
