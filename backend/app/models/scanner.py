from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScannerConditionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["confidence", "risk_reward", "mtf_alignment", "momentum", "volatility", "volume", "direction", "regime", "structure", "liquidity", "signal_status", "trend"]
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "contains", "in"]
    value: str | float | int | bool | list[str]


class ScannerConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_confidence: float | None = Field(default=None, ge=0, le=1)
    min_risk_reward: float | None = Field(default=None, ge=0)
    regimes: list[str] = Field(default_factory=list)
    directions: list[str] = Field(default_factory=list)
    structures: list[str] = Field(default_factory=list)
    min_mtf_alignment: int | None = Field(default=None, ge=0, le=4)
    min_momentum: float | None = None
    max_volatility: float | None = Field(default=None, ge=0)
    min_volume: float | None = Field(default=None, ge=0)
    require_qualified: bool = True
    custom_match: Literal["ALL", "ANY"] = "ALL"
    custom_conditions: list[ScannerConditionRule] = Field(default_factory=list)


class ScannerPresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    asset_universe: list[str] = Field(min_length=1, max_length=50)
    timeframes: list[str] = Field(default_factory=lambda: ["15m", "1h", "4h", "1D"])
    conditions: ScannerConditions = Field(default_factory=ScannerConditions)
    alert_events: list[str] = Field(default_factory=list)


class ScannerPresetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    asset_universe: list[str] | None = Field(default=None, min_length=1, max_length=50)
    timeframes: list[str] | None = None
    conditions: ScannerConditions | None = None
    alert_events: list[str] | None = None
    enabled: bool | None = None


class ScannerPreset(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    asset_universe: list[str]
    timeframes: list[str]
    conditions: ScannerConditions
    alert_events: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ScannerOpportunity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | None = None
    symbol: str
    setup: str
    regime: str | None
    direction: str
    confidence: float
    risk_reward: float | None
    structure: str | None
    liquidity: str | None
    mtf_alignment: int | None
    momentum: float | None
    volatility: float | None
    volume: float | None
    trend: str | None
    entry_price: float | None
    stop_loss: float | None
    target_price: float | None
    last_price: float | None
    signal_status: str
    historical_evidence: dict[str, Any]
    signal_id: str
    observed_at: datetime


class ScannerRun(BaseModel):
    id: str
    preset_id: str
    status: str
    scanned_count: int
    qualified_count: int
    started_at: datetime
    completed_at: datetime | None
    opportunities: list[ScannerOpportunity] = Field(default_factory=list)


class ScannerScheduleCreate(BaseModel):
    preset_id: str
    name: str = Field(min_length=1, max_length=100)
    interval_minutes: int = Field(ge=15, le=10080)
    enabled: bool = True


class ScannerSchedulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    enabled: bool | None = None


class ScannerSchedule(BaseModel):
    id: str
    user_id: str
    preset_id: str
    name: str
    interval_minutes: int
    enabled: bool
    next_run_at: datetime
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
