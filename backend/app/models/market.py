from __future__ import annotations

from datetime import datetime
from enum import Enum
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    """Canonical, validated OHLCV candle used by research calculations."""

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

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def finite_number(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("OHLCV values must be finite numbers.")
        return value

    @field_validator("high")
    @classmethod
    def high_must_not_be_below_open(cls, value: float, info):
        if "open" in info.data and value < info.data["open"]:
            raise ValueError("Candle high cannot be below open.")
        return value

    @field_validator("low")
    @classmethod
    def low_must_not_be_above_open(cls, value: float, info):
        if "open" in info.data and value > info.data["open"]:
            raise ValueError("Candle low cannot be above open.")
        return value

    @field_validator("close")
    @classmethod
    def close_must_be_within_range(cls, value: float, info):
        if "high" in info.data and value > info.data["high"]:
            raise ValueError("Candle close cannot be above high.")
        if "low" in info.data and value < info.data["low"]:
            raise ValueError("Candle close cannot be below low.")
        return value


class OHLCVDataset(BaseModel):
    """Canonical historical dataset passed between market-data and research layers."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    source: str
    requested_at: datetime
    provider_timestamp: datetime | None = None
    candles: tuple[Candle, ...]

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


class IndicatorValue(BaseModel):
    value: float | None
    period: int | None = None


class TechnicalAnalysisResult(BaseModel):
    """Deterministic indicator output with dataset provenance."""

    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    latest_candle_timestamp: datetime
    candle_count: int
    indicators: dict[str, float | None | str]
