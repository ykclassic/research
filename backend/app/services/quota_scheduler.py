from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import Lock
import time


@dataclass(frozen=True)
class QuotaSnapshot:
    minute_remaining: int
    daily_remaining: int
    provider_remaining: int | None
    available: int
    candle_remaining: int = 0


class QuoteQuotaScheduler:
    """Thread-safe scheduler for the shared Twelve Data API credit budget.

    Provider-reported remaining credits represent completed requests. Local
    reservation counters therefore represent only requests currently in flight.
    Quote reservations also preserve the configured protected candle capacity.
    """

    def __init__(self, *, minute_budget: int, daily_budget: int, protected_capacity: int = 0, clock=time.monotonic) -> None:
        if minute_budget < 1 or daily_budget < 1 or protected_capacity < 0:
            raise ValueError("Invalid quote quota budgets")
        self._minute_budget = minute_budget
        self._protected_capacity = min(protected_capacity, minute_budget)
        self._daily_budget = daily_budget
        self._clock = clock
        self._lock = Lock()
        self._minute_started = clock()
        self._minute_reserved = 0
        self._candle_reserved = 0
        self._daily_date = datetime.now(timezone.utc).date()
        self._daily_reserved = 0
        self._provider_remaining: int | None = None
        self._provider_observed_at: datetime | None = None

    def _reset_locked(self) -> None:
        now = self._clock()
        if now - self._minute_started >= 60:
            self._minute_started = now
            self._minute_reserved = 0
            self._candle_reserved = 0
        today = datetime.now(timezone.utc).date()
        if today != self._daily_date:
            self._daily_date = today
            self._daily_reserved = 0

    def _provider_remaining_locked(self) -> int | None:
        if self._provider_remaining is None or self._provider_observed_at is None:
            return None
        age = (datetime.now(timezone.utc) - self._provider_observed_at).total_seconds()
        return self._provider_remaining if 0 <= age < 60 else None

    def _in_flight_locked(self) -> int:
        return self._minute_reserved + self._candle_reserved

    def _shared_remaining_locked(self) -> int:
        local_remaining = max(0, self._minute_budget - self._in_flight_locked())
        provider_remaining = self._provider_remaining_locked()
        if provider_remaining is None:
            return local_remaining
        return min(local_remaining, max(0, provider_remaining - self._in_flight_locked()))

    def _snapshot_locked(self) -> QuotaSnapshot:
        self._reset_locked()
        minute_remaining = max(0, self._minute_budget - self._in_flight_locked())
        candle_remaining = max(0, self._protected_capacity - self._candle_reserved)
        daily_remaining = max(0, self._daily_budget - self._daily_reserved)
        provider_remaining = self._provider_remaining_locked()
        return QuotaSnapshot(
            minute_remaining=minute_remaining,
            daily_remaining=daily_remaining,
            provider_remaining=provider_remaining,
            available=min(minute_remaining, daily_remaining, self._shared_remaining_locked()),
            candle_remaining=candle_remaining,
        )

    def observe_provider_remaining(self, remaining: int | None, observed_at: datetime | None) -> None:
        with self._lock:
            self._provider_remaining = None if remaining is None else max(0, remaining)
            self._provider_observed_at = observed_at

    def snapshot(self) -> QuotaSnapshot:
        with self._lock:
            return self._snapshot_locked()

    def reserve(self, requested: int) -> int:
        if requested <= 0:
            return 0
        with self._lock:
            snapshot = self._snapshot_locked()
            quote_minute_capacity = max(0, self._minute_budget - self._protected_capacity - self._minute_reserved)
            provider_remaining = snapshot.provider_remaining
            if provider_remaining is None:
                provider_capacity = quote_minute_capacity
            else:
                protected_unreserved = max(0, self._protected_capacity - self._candle_reserved)
                provider_capacity = max(
                    0,
                    provider_remaining - self._in_flight_locked() - protected_unreserved,
                )
            granted = min(requested, quote_minute_capacity, snapshot.daily_remaining, provider_capacity)
            self._minute_reserved += granted
            self._daily_reserved += granted
            return granted

    def reserve_candle(self, requested: int = 1) -> int:
        if requested <= 0:
            return 0
        with self._lock:
            snapshot = self._snapshot_locked()
            shared_remaining = self._shared_remaining_locked()
            granted = min(requested, snapshot.candle_remaining, snapshot.daily_remaining, shared_remaining)
            self._candle_reserved += granted
            self._daily_reserved += granted
            return granted

    def reserve_with_protected_capacity(self, requested: int, protected_capacity: int) -> int:
        """Backward-compatible quote reservation that preserves candle capacity."""
        if requested <= 0:
            return 0
        protected_capacity = min(max(0, protected_capacity), self._minute_budget)
        with self._lock:
            snapshot = self._snapshot_locked()
            quote_minute_capacity = max(0, self._minute_budget - protected_capacity - self._minute_reserved)
            provider_remaining = snapshot.provider_remaining
            if provider_remaining is None:
                provider_capacity = quote_minute_capacity
            else:
                protected_unreserved = max(0, protected_capacity - self._candle_reserved)
                provider_capacity = max(
                    0,
                    provider_remaining - self._in_flight_locked() - protected_unreserved,
                )
            granted = min(requested, quote_minute_capacity, snapshot.daily_remaining, provider_capacity)
            self._minute_reserved += granted
            self._daily_reserved += granted
            return granted

    def release(self, count: int) -> None:
        if count <= 0:
            return
        with self._lock:
            self._reset_locked()
            released = min(count, self._minute_reserved, self._daily_reserved)
            self._minute_reserved -= released
            self._daily_reserved -= released

    def reconcile(self, *, provider_remaining: int | None, observed_at: datetime | None) -> None:
        if provider_remaining is not None:
            with self._lock:
                self._provider_remaining = max(0, provider_remaining)
                self._provider_observed_at = observed_at
                self._minute_reserved = 0

    @property
    def daily_date(self) -> date:
        with self._lock:
            self._reset_locked()
            return self._daily_date
