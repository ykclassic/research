from datetime import datetime, timezone

from app.services.quota_scheduler import QuoteQuotaScheduler


def test_provider_remaining_is_not_double_subtracted() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=8, daily_budget=800, protected_capacity=4)
    scheduler.reconcile(
        provider_remaining=7,
        observed_at=datetime.now(timezone.utc),
    )

    # Four credits remain available to quotes while four are protected for
    # candle work; provider telemetry already accounts for completed calls.
    assert scheduler.reserve(4) == 4
    assert scheduler.snapshot().available == 0


def test_four_protected_candle_reservations_can_be_granted_concurrently() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=8, daily_budget=800, protected_capacity=4)
    scheduler.reconcile(
        provider_remaining=8,
        observed_at=datetime.now(timezone.utc),
    )

    grants = [scheduler.reserve_candle(1) for _ in range(4)]

    assert grants == [1, 1, 1, 1]
    assert scheduler.snapshot().candle_remaining == 0
    assert scheduler.reserve(1) == 0


def test_candle_reservation_leaves_quote_capacity_when_provider_has_eight_credits() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=8, daily_budget=800, protected_capacity=4)
    scheduler.reconcile(
        provider_remaining=8,
        observed_at=datetime.now(timezone.utc),
    )

    assert scheduler.reserve_candle(1) == 1
    assert scheduler.reserve(4) == 4
