from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.market import Timeframe


class StructureStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BROKEN = "BROKEN"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


class StructureEvent(BaseModel):
    """Immutable, auditable SMC/market-structure observation.

    ``time`` is the first timestamp at which the event is knowable from the
    completed-candle stream. ``source_candles`` identifies the candles used by
    the detector. No detector may use candles after ``time`` to establish that
    the event occurred.
    """

    model_config = ConfigDict(frozen=True)

    type: str
    price: float = Field(gt=0)
    time: datetime
    timeframe: Timeframe
    strength: float = Field(ge=0, le=1)
    status: StructureStatus
    invalidation: float | None = Field(default=None, gt=0)
    source_candles: tuple[datetime, ...] = Field(min_length=1)


class MarketStructureResult(BaseModel):
    """Deterministic market-structure and SMC research snapshot."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    latest_candle_timestamp: datetime
    candle_count: int = Field(ge=1)
    events: tuple[StructureEvent, ...]

    @property
    def by_type(self) -> dict[str, tuple[StructureEvent, ...]]:
        grouped: dict[str, list[StructureEvent]] = {}
        for event in self.events:
            grouped.setdefault(event.type, []).append(event)
        return {key: tuple(value) for key, value in grouped.items()}
