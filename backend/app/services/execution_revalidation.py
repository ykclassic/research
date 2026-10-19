from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol


class ExecutionRevalidationError(RuntimeError):
    """A mandatory pre-execution check failed; execution must not proceed."""


@dataclass(frozen=True)
class RevalidationLimits:
    market_max_age: timedelta = timedelta(seconds=15)
    account_max_age: timedelta = timedelta(seconds=30)
    risk_max_age: timedelta = timedelta(seconds=30)
    provider_timeout_seconds: float = 5.0
    max_entry_drift_pct: float = 0.25
    max_risk_pct: float = 0.75
    max_daily_loss_pct: float = 2.0
    max_correlated_positions: int = 2
    min_reward_risk: float = 2.0
    max_clock_skew: timedelta = timedelta(seconds=2)


class AccountSnapshotProvider(Protocol):
    async def get_account_snapshot(self, user_id: str, account_ref: str) -> Mapping[str, Any]: ...


class MarketSnapshotProvider(Protocol):
    async def get_market_snapshot(self, symbol: str) -> Mapping[str, Any]: ...


class RiskSnapshotProvider(Protocol):
    async def evaluate_risk(
        self,
        intent: Mapping[str, Any],
        account_snapshot: Mapping[str, Any],
        market_snapshot: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RevalidationProviders:
    account: AccountSnapshotProvider | None
    market: MarketSnapshotProvider | None
    risk: RiskSnapshotProvider | None


def _parse_timestamp(snapshot: Mapping[str, Any], label: str) -> datetime:
    raw = snapshot.get("observed_at")
    if not isinstance(raw, str) or not raw.strip():
        raise ExecutionRevalidationError(f"{label} snapshot has no observation timestamp.")
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionRevalidationError(f"{label} snapshot timestamp is invalid.") from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ExecutionRevalidationError(f"{label} snapshot timestamp must include a timezone.")
    return observed.astimezone(timezone.utc)


def _require_fresh(
    snapshot: Mapping[str, Any],
    label: str,
    max_age: timedelta,
    now: datetime,
    max_clock_skew: timedelta,
) -> None:
    observed = _parse_timestamp(snapshot, label)
    age = now - observed
    if age < -max_clock_skew or age > max_age:
        raise ExecutionRevalidationError(f"{label} snapshot is stale or from the future.")


def revalidate_execution_snapshots(
    *,
    intent: Mapping[str, Any],
    account: Mapping[str, Any],
    market: Mapping[str, Any],
    risk: Mapping[str, Any],
    now: datetime | None = None,
    limits: RevalidationLimits = RevalidationLimits(),
) -> dict[str, Any]:
    """Validate fresh state against the approved intent. Never invokes an adapter."""
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ExecutionRevalidationError("Validation clock must be timezone-aware.")
    checked_at = clock.astimezone(timezone.utc)

    for snapshot, label, max_age in (
        (account, "Account", limits.account_max_age),
        (market, "Market", limits.market_max_age),
        (risk, "Risk", limits.risk_max_age),
    ):
        if not isinstance(snapshot, Mapping) or not snapshot:
            raise ExecutionRevalidationError(f"{label} snapshot is missing.")
        _require_fresh(snapshot, label, max_age, checked_at, limits.max_clock_skew)

    if account.get("execution_enabled") is not True:
        raise ExecutionRevalidationError("Execution is disabled for this account.")
    equity = account.get("equity")
    daily_loss_pct = account.get("daily_loss_pct")
    correlated_positions = account.get("correlated_open_positions")
    if not isinstance(equity, (int, float)) or isinstance(equity, bool) or equity <= 0:
        raise ExecutionRevalidationError("Authoritative account equity is unavailable.")
    if not isinstance(daily_loss_pct, (int, float)) or isinstance(daily_loss_pct, bool):
        raise ExecutionRevalidationError("Current daily drawdown is unavailable.")
    if daily_loss_pct < 0 or daily_loss_pct >= limits.max_daily_loss_pct:
        raise ExecutionRevalidationError("Daily loss limit blocks execution.")
    if not isinstance(correlated_positions, int) or isinstance(correlated_positions, bool):
        raise ExecutionRevalidationError("Current correlated position count is unavailable.")
    if correlated_positions >= limits.max_correlated_positions:
        raise ExecutionRevalidationError("Correlated position limit blocks execution.")

    symbol = intent.get("symbol")
    side = intent.get("side")
    entry = intent.get("entry_price")
    stop = intent.get("stop_loss")
    target = intent.get("take_profit")
    quantity = intent.get("quantity")
    request_hash = intent.get("request_hash")
    policy_version = intent.get("risk_policy_version")
    account_ref = intent.get("account_ref")
    if not all((isinstance(symbol, str) and symbol, side in {"LONG", "SHORT"}, isinstance(request_hash, str) and request_hash, isinstance(policy_version, str) and policy_version, isinstance(account_ref, str) and account_ref, isinstance(quantity, (int, float)) and not isinstance(quantity, bool) and quantity > 0)):
        raise ExecutionRevalidationError("Approved intent is incomplete.")
    if account.get("account_ref") != account_ref:
        raise ExecutionRevalidationError("Fresh account does not match the approved account.")
    if market.get("symbol") != symbol or market.get("tradable") is not True:
        raise ExecutionRevalidationError("Market is not currently tradable for the approved symbol.")

    price = market.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        raise ExecutionRevalidationError("Fresh market price is unavailable.")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 for value in (entry, stop, target)):
        raise ExecutionRevalidationError("Approved entry, stop, or target is invalid.")
    drift_pct = abs(float(price) / float(entry) - 1.0) * 100
    if drift_pct > limits.max_entry_drift_pct:
        raise ExecutionRevalidationError("Market price moved beyond the approved entry tolerance.")

    if side == "LONG":
        if not float(stop) < float(entry) < float(target):
            raise ExecutionRevalidationError("Long stop/target structure is invalid.")
        risk_distance = float(entry) - float(stop)
        reward_distance = float(target) - float(entry)
    else:
        if not float(target) < float(entry) < float(stop):
            raise ExecutionRevalidationError("Short stop/target structure is invalid.")
        risk_distance = float(stop) - float(entry)
        reward_distance = float(entry) - float(target)
    if risk_distance <= 0 or reward_distance / risk_distance < limits.min_reward_risk:
        raise ExecutionRevalidationError("Approved setup no longer meets minimum reward-to-risk.")

    risk_pct = risk.get("risk_pct")
    if risk.get("qualified") is not True:
        raise ExecutionRevalidationError("Risk engine did not qualify the proposal.")
    if risk.get("request_hash") != request_hash or risk.get("risk_policy_version") != policy_version:
        raise ExecutionRevalidationError("Risk decision does not match the approved proposal or policy version.")
    if not isinstance(risk_pct, (int, float)) or isinstance(risk_pct, bool) or risk_pct <= 0 or risk_pct > limits.max_risk_pct:
        raise ExecutionRevalidationError("Current per-trade risk exceeds policy.")

    recomputed_quantity = risk.get("recomputed_quantity")
    if not isinstance(recomputed_quantity, (int, float)) or isinstance(recomputed_quantity, bool) or recomputed_quantity <= 0:
        raise ExecutionRevalidationError("Risk engine did not provide a fresh position size.")
    if abs(float(recomputed_quantity) - float(quantity)) > max(1e-9, abs(float(quantity)) * 1e-8):
        raise ExecutionRevalidationError("Fresh risk sizing differs from the human-approved quantity.")

    return {
        # This is a diagnostic result, not an execution authorization token.
        # SQL claim remains hard-disabled until provider provenance is integrated.
        "passed": True,
        "validated_at": checked_at.isoformat(),
        "account_observed_at": _parse_timestamp(account, "Account").isoformat(),
        "market_observed_at": _parse_timestamp(market, "Market").isoformat(),
        "risk_observed_at": _parse_timestamp(risk, "Risk").isoformat(),
        "account_ref": account_ref,
        "symbol": symbol,
        "side": side,
        "quantity": float(quantity),
        "entry_price": float(entry),
        "stop_loss": float(stop),
        "take_profit": float(target),
        "market_price": float(price),
        "entry_drift_pct": drift_pct,
        "equity": float(equity),
        "risk_pct": float(risk_pct),
        "risk_policy_version": policy_version,
        "request_hash": request_hash,
    }


async def revalidate_before_execution(
    *,
    user_id: str,
    intent: Mapping[str, Any],
    providers: RevalidationProviders,
    now: datetime | None = None,
    limits: RevalidationLimits = RevalidationLimits(),
) -> dict[str, Any]:
    """Fetch all mandatory state under a deadline and fail closed on errors."""
    if providers.account is None or providers.market is None or providers.risk is None:
        raise ExecutionRevalidationError("Required account, market, and risk providers are not configured.")
    account_ref = intent.get("account_ref")
    symbol = intent.get("symbol")
    if not isinstance(account_ref, str) or not account_ref or not isinstance(symbol, str) or not symbol:
        raise ExecutionRevalidationError("Approved intent lacks account or symbol identity.")
    if limits.provider_timeout_seconds <= 0:
        raise ExecutionRevalidationError("Provider timeout must be positive.")

    async def _fetch_and_evaluate() -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
        account, market = await asyncio.gather(
            providers.account.get_account_snapshot(user_id, account_ref),
            providers.market.get_market_snapshot(symbol),
        )
        risk = await providers.risk.evaluate_risk(intent, account, market)
        return account, market, risk

    try:
        account, market, risk = await asyncio.wait_for(
            _fetch_and_evaluate(), timeout=limits.provider_timeout_seconds
        )
    except Exception as exc:
        raise ExecutionRevalidationError(
            "Required fresh account, market, or risk state could not be verified."
        ) from exc
    return revalidate_execution_snapshots(
        intent=intent, account=account, market=market, risk=risk, now=now, limits=limits
    )
