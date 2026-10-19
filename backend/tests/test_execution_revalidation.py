from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.execution_revalidation import (
    ExecutionRevalidationError,
    RevalidationProviders,
    revalidate_before_execution,
    revalidate_execution_snapshots,
)


NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _stamp(seconds_ago: int = 0) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def _snapshots():
    intent = {
        "account_ref": "exchange-account-1",
        "symbol": "BTC/USDT",
        "side": "LONG",
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "quantity": 0.1,
        "risk_policy_version": "risk-v1",
        "request_hash": "a" * 64,
    }
    account = {
        "observed_at": _stamp(),
        "account_ref": "exchange-account-1",
        "execution_enabled": True,
        "equity": 10000.0,
        "daily_loss_pct": 0.5,
        "correlated_open_positions": 1,
    }
    market = {
        "observed_at": _stamp(),
        "symbol": "BTC/USDT",
        "tradable": True,
        "price": 100.1,
    }
    risk = {
        "observed_at": _stamp(),
        "qualified": True,
        "request_hash": "a" * 64,
        "risk_policy_version": "risk-v1",
        "risk_pct": 0.5,
        "recomputed_quantity": 0.1,
    }
    return intent, account, market, risk


def test_revalidation_passes_only_when_all_fresh_snapshots_match_approved_intent() -> None:
    intent, account, market, risk = _snapshots()

    result = revalidate_execution_snapshots(
        intent=intent, account=account, market=market, risk=risk, now=NOW
    )

    assert result["request_hash"] == intent["request_hash"]
    assert result["risk_policy_version"] == "risk-v1"
    assert result["entry_drift_pct"] == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("snapshot_name", "mutation", "message"),
    [
        ("account", lambda s: s.update(equity=0), "equity"),
        ("account", lambda s: s.update(execution_enabled=False), "disabled"),
        ("account", lambda s: s.update(daily_loss_pct=2.0), "Daily loss"),
        ("account", lambda s: s.update(correlated_open_positions=2), "Correlated"),
        ("account", lambda s: s.update(observed_at=_stamp(31)), "stale"),
        ("market", lambda s: s.update(tradable=False), "not currently tradable"),
        ("market", lambda s: s.update(price=101.0), "moved beyond"),
        ("market", lambda s: s.update(observed_at=_stamp(16)), "stale"),
        ("risk", lambda s: s.update(qualified=False), "did not qualify"),
        ("risk", lambda s: s.update(risk_pct=0.76), "per-trade risk"),
        ("risk", lambda s: s.update(recomputed_quantity=0.2), "differs from the human-approved quantity"),
        ("risk", lambda s: s.update(risk_policy_version="old-policy"), "does not match"),
        ("risk", lambda s: s.update(observed_at=_stamp(31)), "stale"),
    ],
)
def test_any_failed_account_market_or_risk_check_blocks_execution(
    snapshot_name, mutation, message
) -> None:
    intent, account, market, risk = _snapshots()
    snapshots = {"account": account, "market": market, "risk": risk}
    mutation(snapshots[snapshot_name])

    with pytest.raises(ExecutionRevalidationError, match=message):
        revalidate_execution_snapshots(
            intent=intent, account=account, market=market, risk=risk, now=NOW
        )


def test_missing_or_naive_timestamp_fails_closed() -> None:
    intent, account, market, risk = _snapshots()
    del market["observed_at"]
    with pytest.raises(ExecutionRevalidationError, match="timestamp"):
        revalidate_execution_snapshots(
            intent=intent, account=account, market=market, risk=risk, now=NOW
        )

    market["observed_at"] = "2026-10-19T12:00:00"
    with pytest.raises(ExecutionRevalidationError, match="timezone"):
        revalidate_execution_snapshots(
            intent=intent, account=account, market=market, risk=risk, now=NOW
        )


class _Account:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    async def get_account_snapshot(self, user_id, account_ref):
        return self.snapshot


class _Market:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    async def get_market_snapshot(self, symbol):
        return self.snapshot


class _Risk:
    def __init__(self, snapshot=None, fail=False):
        self.snapshot = snapshot
        self.fail = fail

    async def evaluate_risk(self, intent, account_snapshot, market_snapshot):
        if self.fail:
            raise TimeoutError("provider secret detail must not be exposed")
        return self.snapshot


@pytest.mark.asyncio
async def test_unconfigured_provider_fails_closed() -> None:
    intent, _, _, _ = _snapshots()
    with pytest.raises(ExecutionRevalidationError, match="providers are not configured"):
        await revalidate_before_execution(
            user_id="user-1", intent=intent,
            providers=RevalidationProviders(account=None, market=None, risk=None), now=NOW,
        )


@pytest.mark.asyncio
async def test_provider_failure_fails_closed_without_leaking_exception() -> None:
    intent, account, market, _ = _snapshots()
    providers = RevalidationProviders(
        account=_Account(account), market=_Market(market), risk=_Risk(fail=True)
    )
    with pytest.raises(ExecutionRevalidationError, match="could not be verified") as error:
        await revalidate_before_execution(
            user_id="user-1", intent=intent, providers=providers, now=NOW
        )
    assert "provider secret detail" not in str(error.value)


@pytest.mark.asyncio
async def test_missing_risk_snapshot_fails_closed() -> None:
    intent, account, market, _ = _snapshots()
    providers = RevalidationProviders(
        account=_Account(account), market=_Market(market), risk=_Risk(snapshot={})
    )
    with pytest.raises(ExecutionRevalidationError, match="snapshot is missing"):
        await revalidate_before_execution(
            user_id="user-1", intent=intent, providers=providers, now=NOW
        )
