from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user_or_github_actions, require_github_actions
from app.config import settings
from app.services.entitlement import UsageLimitExceededError, consume_usage, require_feature
from app.services.research_copilot import ResearchCopilotError, ResearchCopilotService, interpret_query
from app.services.research_workspace import run_due_automation_rules
from app.services.phase9_infrastructure import deliver_pending_webhooks, run_due_export_schedules
from app.services.phase10_intelligence import run_maintenance

router = APIRouter(prefix="/api/research-copilot", tags=["research-copilot"])
service = ResearchCopilotService()


class CopilotRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    default_symbol: str = Field(default="BTC/USD", min_length=3, max_length=32)


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=3, max_length=4000)
    interval_minutes: int = Field(ge=60, le=10080)


class CopilotResponse(BaseModel):
    run_id: str
    query: str
    assets: list[str]
    timeframe: str
    intent: str
    claim: str
    report: str
    evidence: list[dict]
    sources: list[dict]
    methodology: str
    model: str
    model_version: str
    engine_version: str
    timestamp: str | None = None
    limitations: list[str]


@router.post("/run", response_model=CopilotResponse, dependencies=[Depends(_require_csrf)])
async def run_copilot(request: CopilotRequest, user: UserResponse | None = Depends(get_current_user_or_github_actions), access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None) -> CopilotResponse:
    if user is None or not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        require_feature(access_token, user.id, "ai_research")
        interpretation = interpret_query(request.query, request.default_symbol)
        if interpretation["days"] > 7 or interpretation["intent"] in {"comparison", "historical_setup"}:
            require_feature(access_token, user.id, "copilot_deep_research")
            consume_usage(access_token, user.id, "historical_queries", 1)
        if len(interpretation["assets"]) > 2 or "multi-step" in request.query.lower() or "workflow" in request.query.lower():
            require_feature(access_token, user.id, "copilot_multi_step")
        consume_usage(access_token, user.id, "copilot_research_runs", 1)
    except UsageLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    try:
        result = await service.run(access_token, user.id, request.query, request.default_symbol)
        return CopilotResponse(**result)
    except ResearchCopilotError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (RuntimeError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/history")
async def copilot_history(user: UserResponse | None = Depends(get_current_user_or_github_actions), access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None) -> list[dict]:
    if user is None or not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return service.history(access_token, user.id)


@router.post("/scheduler/run", dependencies=[Depends(require_github_actions)])
async def copilot_scheduler(x_research_copilot_secret: Annotated[str | None, Header()] = None) -> dict[str, str]:
    if not settings.scanner_scheduler_secret or not x_research_copilot_secret or not secrets.compare_digest(x_research_copilot_secret, settings.scanner_scheduler_secret):
        raise HTTPException(status_code=401, detail="Invalid research copilot scheduler credential.")
    try:
        scheduled = await service.run_due_schedules(settings.supabase_service_role_key)
        workspace = await run_due_automation_rules(settings.supabase_service_role_key)
        webhooks = deliver_pending_webhooks()
        exports = run_due_export_schedules()
        maintenance = run_maintenance()
        return {**scheduled, "workspace_scheduled": workspace["scheduled"], "workspace_completed": workspace["completed"], "workspace_failed": workspace["failed"], "webhook_processed": webhooks["processed"], "webhook_delivered": webhooks["delivered"], "webhook_failed": webhooks["failed"], "export_scheduled": exports["scheduled"], "export_completed": exports["completed"], "export_failed": exports["failed"], "cache_expired": maintenance["expired_cache_entries"], "failed": scheduled["failed"] + workspace["failed"] + webhooks["failed"] + exports["failed"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Scheduled research execution failed.") from exc


@router.get("/schedules")
async def schedules(user: UserResponse | None = Depends(get_current_user_or_github_actions), access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    if user is None or not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return service.list_schedules(access_token, user.id)


@router.post("/schedules", dependencies=[Depends(_require_csrf)])
async def create_schedule(request: ScheduleRequest, user: UserResponse | None = Depends(get_current_user_or_github_actions), access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    if user is None or not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        require_feature(access_token, user.id, "scheduled_workflows")
        return service.create_schedule(access_token, user.id, request.name, request.query, request.interval_minutes)
    except Exception as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}", dependencies=[Depends(_require_csrf)])
async def delete_schedule(schedule_id: str, user: UserResponse | None = Depends(get_current_user_or_github_actions), access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    if user is None or not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    service.delete_schedule(access_token, user.id, schedule_id)
    return {"deleted": True}
