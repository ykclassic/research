from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CacheEntry(Generic[T]):
    value: T
    stored_at: float
    fresh_until: float
    stale_until: float

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.stored_at)

    @property
    def fresh(self) -> bool:
        return time.monotonic() < self.fresh_until

    @property
    def usable_stale(self) -> bool:
        return time.monotonic() < self.stale_until


class CanonicalMarketCache(Generic[T]):
    """Provider-independent last-known-good cache.

    The cache is intentionally the only cache consulted by the orchestration layer.
    Provider-specific responses are validated before entering it. A stale entry is
    never relabeled as live data; callers receive explicit stale/cache metadata.
    """

    def __init__(self) -> None:
        self._items: dict[str, CacheEntry[T]] = {}

    def get(self, key: str, *, allow_stale: bool = False) -> tuple[T, float] | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if entry.fresh or (allow_stale and entry.usable_stale):
            return entry.value, entry.age_seconds
        self._items.pop(key, None)
        return None

    def set(self, key: str, value: T, fresh_ttl_seconds: float, stale_ttl_seconds: float) -> None:
        now = time.monotonic()
        self._items[key] = CacheEntry(
            value=value,
            stored_at=now,
            fresh_until=now + max(0.0, fresh_ttl_seconds),
            stale_until=now + max(fresh_ttl_seconds, stale_ttl_seconds),
        )

    def clear(self) -> None:
        self._items.clear()

    def size(self) -> int:
        return len(self._items)


# Backwards-compatible generic cache used by unrelated application code.
class TTLCache(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        result = self._items.get(key)
        if result is None or not result.fresh:
            self._items.pop(key, None)
            return None
        return result.value

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        self._items[key] = CacheEntry(
            value=value,
            stored_at=time.monotonic(),
            fresh_until=time.monotonic() + ttl_seconds,
            stale_until=time.monotonic() + ttl_seconds,
        )
