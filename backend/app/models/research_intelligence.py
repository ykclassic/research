from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ProvenanceRecord(BaseModel):
    id: str
    snapshot_id: str
    claim_type: str
    claim: str
    analysis: str
    data: dict[str, object] = Field(default_factory=dict)
    sources: tuple[str, ...] = ()
    observed_at: datetime
    method: str
    engine_version: str


class ResearchSnapshot(BaseModel):
    id: str
    symbol: str
    snapshot_type: str
    snapshot_at: datetime
    source_history_id: str | None = None
    state: dict[str, object] = Field(default_factory=dict)
    engine_version: str
    provenance: tuple[ProvenanceRecord, ...] = ()


class ChangeItem(BaseModel):
    category: str
    field: str
    previous: object | None = None
    current: object | None = None
    significance: str = "OBSERVED"


class ResearchComparison(BaseModel):
    symbol: str
    baseline_type: str
    current: ResearchSnapshot
    baseline: ResearchSnapshot | None = None
    changes: tuple[ChangeItem, ...] = ()
    summary: str
    evidence_note: str


class Watchpoint(BaseModel):
    id: str
    symbol: str
    name: str
    condition_type: str
    field: str
    operator: str
    value: object | None = None
    timeframe: str | None = None
    enabled: bool
    last_state: bool | None = None
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WatchpointEvent(BaseModel):
    id: str
    watchpoint_id: str
    symbol: str
    event_type: str
    message: str
    observed_value: object | None = None
    triggered_at: datetime


class CatalystRecord(BaseModel):
    id: str
    title: str
    event_type: str
    source: str
    source_url: str | None = None
    event_timestamp: datetime
    affected_assets: tuple[str, ...] = ()
    sentiment: str | None = None
    market_reaction: dict[str, object] = Field(default_factory=dict)
    provider: str
