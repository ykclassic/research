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


class QuoteQuotaScheduler:
    """Thread-safe reservation scheduler for quote work."""

    def __init__(self, *, minute_budget: int, daily_budget: int, clock=time.monotonic) -> None:
        if minute_budget < 1 or daily_budget < minute_budget:
            raise ValueError("Invalid quote quota budgets")
        self._minute_budget = minute_budget
        self._daily_budget = daily_budget
        self._clock = clock
        self._lock = Lock()
        self._minute_started = clock()
        self._minute_reserved = 0
        self._daily_date = datetime.now(timezone.utc).date()
        self._daily_reserved = 0
        self._provider_remaining: int | None = None
        self._provider_observed_at: datetime | None = None

    def _reset_locked(self) -> None:
        now = self._clock()
        if now - self._minute_started >= 60:
            self._minute_started = now
            self._minute_reserved = 0
        today = datetime.now(timezone.utc).date()
        if today != self._daily_date:
            self._daily_date = today
            self._daily_reserved = 0

    def _snapshot_locked(self) -> QuotaSnapshot:
        self._reset_locked()
        minute_remaining = max(0, self._minute_budget - self._minute_reserved)
        daily_remaining = max(0, self._daily_budget - self._daily_reserved)
        provider_remaining = None
        if self._provider_remaining is not None and self._provider_observed_at is not None:
            age = (datetime.now(timezone.utc) - self._provider_observed_at).total_seconds()
            if 0 <= age < 60:
                provider_remaining = self._provider_remaining
        limits = [minute_remaining, daily_remaining]
        if provider_remaining is not None:
            limits.append(provider_remaining)
        return QuotaSnapshot(minute_remaining, daily_remaining, provider_remaining, min(limits))

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
            granted = min(requested, snapshot.available)
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
            self.observe_provider_remaining(provider_remaining, observed_at)

    @property
    def daily_date(self) -> date:
        with self._lock:
            self._reset_locked()
            return self._daily_date
