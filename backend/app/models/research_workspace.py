from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal

WorkspaceType = Literal["CRYPTO","EQUITIES","FX","SECTOR","STRATEGY","THEME","PORTFOLIO","CUSTOM"]
ResourceType = Literal["WATCHLIST","RESEARCH_RUN","REPORT","ALERT","WATCHPOINT","EXPERIMENT"]

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    workspace_type: WorkspaceType = "THEME"
    description: str = Field(default="", max_length=1000)
    shared: bool = False

class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    workspace_type: WorkspaceType | None = None
    description: str | None = Field(default=None, max_length=1000)
    shared: bool | None = None

class WorkspaceAsset(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    role: Literal["PRIMARY","COMPARISON","BENCHMARK","WATCH"] = "PRIMARY"

class DashboardUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    layout: dict[str, Any] = Field(default_factory=lambda: {"columns": 12, "rows": []})
    widgets: list[dict[str, Any]] = Field(default_factory=list)
    saved_views: list[dict[str, Any]] = Field(default_factory=list)
    custom_metrics: list[dict[str, Any]] = Field(default_factory=list)
    shared: bool = False

class WorkspaceLink(BaseModel):
    resource_type: ResourceType
    resource_id: str

class ScorecardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    factors: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    scoring_rules: dict[str, Any] = Field(default_factory=dict)

class AutomationRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trigger_type: Literal["SCHEDULE","REGIME_CHANGE","PRICE_THRESHOLD","SCORE_THRESHOLD","WATCHPOINT"]
    schedule_cron: str | None = None
    symbol: str | None = Field(default=None, max_length=32)
    condition: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=lambda: {"type": "RESEARCH_RUN"})
    enabled: bool = True

class CrossAssetRequest(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=20)
    timeframe: Literal["1h","4h","1d"] = "1d"

class ScorecardEvaluationRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)

class StrategyDiagnosisRequest(BaseModel):
    experiment_id: str

class WorkspaceSnapshot(BaseModel):
    workspace: dict[str, Any]
    assets: list[dict[str, Any]]
    dashboards: list[dict[str, Any]]
    links: list[dict[str, Any]]
    scorecards: list[dict[str, Any]]
    automation: list[dict[str, Any]]
