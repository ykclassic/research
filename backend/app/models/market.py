from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    DELAYED = "DELAYED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class CompletenessStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class Timeframe(str, Enum):
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"

    @property
    def seconds(self) -> int:
        return {
            Timeframe.MINUTE_5: 300,
            Timeframe.MINUTE_15: 900,
            Timeframe.MINUTE_30: 1800,
            Timeframe.HOUR_1: 3600,
            Timeframe.HOUR_4: 14400,
            Timeframe.DAY_1: 86400,
        }[self]


class Candle(BaseModel):
    """Canonical, immutable OHLCV candle used by all research calculations."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)
    symbol: str
    timeframe: Timeframe
    source: str
    is_complete: bool

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Candle timestamp must be timezone-aware.")
        return value.astimezone(timezone.utc)

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def finite_number(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("OHLCV values must be finite numbers.")
        return value

    @model_validator(mode="after")
    def validate_price_range(self) -> Candle:
        if self.high < max(self.open, self.close):
            raise ValueError("Candle high must be >= open and close.")
        if self.low > min(self.open, self.close):
            raise ValueError("Candle low must be <= open and close.")
        if self.high < self.low:
            raise ValueError("Candle high must be >= low.")
        return self


class OHLCVDataset(BaseModel):
    """Canonical historical dataset with explicit freshness/completeness/provenance."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    source: str
    requested_at: datetime
    provider_timestamp: datetime | None = None
    candles: tuple[Candle, ...]
    request_latency_ms: int | None = Field(default=None, ge=0)
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    freshness_age_seconds: float | None = Field(default=None, ge=0)
    completeness_status: CompletenessStatus = CompletenessStatus.UNKNOWN
    fallback_used: bool = False
    provider_attempts: tuple[str, ...] = ()
    cache_hit: bool = False
    cache_age_seconds: float | None = Field(default=None, ge=0)

    @field_validator("requested_at", "provider_timestamp")
    @classmethod
    def metadata_timestamp_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Dataset timestamps must be timezone-aware.")
        return value.astimezone(timezone.utc)

    @field_validator("candles")
    @classmethod
    def validate_candles(cls, candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
        if not candles:
            raise ValueError("OHLCV dataset must contain at least one candle.")
        previous: datetime | None = None
        for candle in candles:
            if previous is not None and candle.timestamp <= previous:
                raise ValueError("OHLCV candle timestamps must be strictly increasing.")
            previous = candle.timestamp
        return candles

    @model_validator(mode="after")
    def validate_candle_identity(self) -> OHLCVDataset:
        for candle in self.candles:
            if candle.symbol != self.symbol:
                raise ValueError("Every candle must match the dataset symbol.")
            if candle.timeframe != self.timeframe:
                raise ValueError("Every candle must match the dataset timeframe.")
            if candle.source != self.source:
                raise ValueError("Every candle must match the dataset source.")
        return self

    @property
    def latest_candle(self) -> Candle:
        return self.candles[-1]

    @property
    def completed_candles(self) -> tuple[Candle, ...]:
        return tuple(candle for candle in self.candles if candle.is_complete)

    @property
    def latest_completed_candle(self) -> Candle | None:
        for candle in reversed(self.candles):
            if candle.is_complete:
                return candle
        return None


class TechnicalAnalysisResult(BaseModel):
    """Deterministic indicator output with dataset provenance."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    latest_candle_timestamp: datetime
    candle_count: int = Field(ge=1)
    indicators: dict[str, float | None | str]
