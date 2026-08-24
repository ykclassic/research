import time
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._items.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        self._items[key] = CacheEntry(
            value=value,
            expires_at=time.monotonic() + ttl_seconds,
        )
