from datetime import datetime, timezone

from app.services.quota_scheduler import QuoteQuotaScheduler


def test_failed_candle_reservation_can_be_released() -> None:
    scheduler = QuoteQuotaScheduler(minute_budget=4, daily_budget=800, protected_capacity=4)

    assert scheduler.reserve_candle(1) == 1
    scheduler.release_candle(1)

    assert scheduler.snapshot().candle_remaining == 4
    assert scheduler.reserve_candle(4) == 4


def test_zero_provider_balance_recovers_after_minute_reset() -> None:
    now = [1000.0]
    scheduler = QuoteQuotaScheduler(
        minute_budget=4,
        daily_budget=800,
        protected_capacity=4,
        clock=lambda: now[0],
    )
    scheduler.reconcile(provider_remaining=0, observed_at=datetime.now(timezone.utc))
    assert scheduler.reserve_candle(1) == 0

    # Provider credits reset at the start of the next minute.
    now[0] += 60.0
    assert scheduler.reserve_candle(1) == 1
