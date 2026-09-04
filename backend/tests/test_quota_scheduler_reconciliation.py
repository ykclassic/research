from datetime import datetime, timezone

from app.services.quota_scheduler import QuoteQuotaScheduler


def test_provider_telemetry_does_not_double_count_completed_quote_reservation() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=8, daily_budget=800, protected_capacity=4)

    assert scheduler.reserve(1) == 1
    scheduler.reconcile(
        provider_remaining=5,
        observed_at=datetime.now(timezone.utc),
    )

    # The provider's remaining-credit value already includes the completed
    # request, so the local reservation must not consume that same credit a
    # second time. Four protected candle credits remain available.
    assert scheduler.reserve(1) == 1
    assert scheduler.reserve_candle(1) == 1


def test_candle_reservations_remain_protected_after_quote_reconciliation() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=8, daily_budget=800, protected_capacity=4)

    assert scheduler.reserve_candle(4) == 4
    scheduler.reconcile(
        provider_remaining=4,
        observed_at=datetime.now(timezone.utc),
    )

    snapshot = scheduler.snapshot()
    assert snapshot.candle_remaining == 0
    assert snapshot.available == 0
