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

    Quote capacity keeps its historical four-credit view while a separate
    protected candle reservation is tracked against the same provider balance.
    This prevents quote traffic from consuming the four credits reserved for
    Daily/H4/H1/M15 MTF candle requests.
    """

    def __init__(self, *, minute_budget: int, daily_budget: int, protected_capacity: int = 0, clock=time.monotonic) -> None:
        if minute_budget < 1 or daily_budget < 1 or protected_capacity < 0:
            raise ValueError("Invalid quote quota budgets")
        self._minute_budget = minute_budget
        self._protected_capacity = protected_capacity
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

    def _snapshot_locked(self) -> QuotaSnapshot:
        self._reset_locked()
        minute_remaining = max(0, self._minute_budget - self._minute_reserved)
        candle_remaining = max(0, self._protected_capacity - self._candle_reserved)
        daily_remaining = max(0, self._daily_budget - self._daily_reserved)
        provider_remaining = self._provider_remaining_locked()
        limits = [minute_remaining, daily_remaining]
        if provider_remaining is not None:
            limits.append(max(0, provider_remaining - self._minute_reserved - self._candle_reserved))
        return QuotaSnapshot(minute_remaining, daily_remaining, provider_remaining, min(limits), candle_remaining)

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
            provider_headroom = snapshot.provider_remaining
            if provider_headroom is not None:
                provider_headroom = max(0, provider_headroom - self._candle_reserved - self._minute_reserved)
            limits = [snapshot.minute_remaining, snapshot.daily_remaining]
            if provider_headroom is not None:
                limits.append(provider_headroom)
            granted = min([requested, *limits])
            self._minute_reserved += granted
            self._daily_reserved += granted
            return granted

    def reserve_candle(self, requested: int = 1) -> int:
        if requested <= 0:
            return 0
        with self._lock:
            snapshot = self._snapshot_locked()
            provider_headroom = snapshot.provider_remaining
            if provider_headroom is not None:
                provider_headroom = max(0, provider_headroom - self._candle_reserved - self._minute_reserved)
            daily_headroom = snapshot.daily_remaining
            limits = [snapshot.candle_remaining, daily_headroom]
            if provider_headroom is not None:
                limits.append(provider_headroom)
            granted = min([requested, *limits])
            self._candle_reserved += granted
            self._daily_reserved += granted
            return granted

    def reserve_with_protected_capacity(self, requested: int, protected_capacity: int) -> int:
        """Backward-compatible quote reservation that preserves candle capacity."""
        if requested <= 0:
            return 0
        protected_capacity = max(0, protected_capacity)
        with self._lock:
            snapshot = self._snapshot_locked()
            provider_headroom = snapshot.provider_remaining
            if provider_headroom is not None:
                provider_headroom = max(0, provider_headroom - self._candle_reserved - self._minute_reserved)
            grantable = max(0, snapshot.minute_remaining - protected_capacity)
            limits = [grantable, snapshot.daily_remaining]
            if provider_headroom is not None:
                limits.append(provider_headroom)
            granted = min([requested, *limits])
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
