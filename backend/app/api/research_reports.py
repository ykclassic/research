from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user_or_github_actions
from app.models.research_report import ResearchReport
from app.preferences.service import preferences_service
from app.services.research_history import create_history_record
from app.services.research_preferences import resolve_research_preferences
from app.services.research_report import ResearchReportService
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/research-reports", tags=["research-reports"], dependencies=[Depends(get_current_user_or_github_actions)])
service = ResearchReportService()


def _resolve_configuration(
    user: UserResponse | None,
    access_token: str | None,
):
    if user is None or not access_token:
        return resolve_research_preferences(None)
    record = preferences_service.get_or_create(access_token, user.id)
    return resolve_research_preferences(record)


async def _generate_report(
    symbol: str | None,
    user: UserResponse | None,
    access_token: str | None,
) -> ResearchReport:
    try:
        configuration = _resolve_configuration(user, access_token)
        report = await service.generate(symbol, configuration=configuration)
        # GitHub OIDC callers validate the report but do not own user history.
        if user is not None and access_token:
            try:
                if preferences_service.get_or_create(access_token, user.id).privacy_preferences.get("save_generated_reports", True):
                    saved = create_history_record(
                        access_token,
                        user.id,
                        record_type="REPORT",
                        symbol=report.symbol,
                        title=f"{report.symbol} Market Research",
                        payload=report.model_dump(mode="json"),
                    )
                    if preferences_service.get_or_create(access_token, user.id).privacy_preferences.get("save_search_history", True):
                        create_history_record(
                            access_token,
                            user.id,
                            record_type="SEARCH",
                            symbol=report.symbol,
                            query=report.symbol,
                            title=f"Research search · {report.symbol}",
                            payload={"report_history_id": saved["id"], "symbol": report.symbol},
                        )
            except DataServiceError:
                # Research generation remains available if persistence is temporarily unavailable.
                pass
        return report
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the research-report latency budget.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=ResearchReport)
async def get_default_research_report(
    user: UserResponse | None = Depends(get_current_user_or_github_actions),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> ResearchReport:
    """Generate research for the authenticated user's configured default asset."""
    return await _generate_report(None, user, access_token)


@router.get("/{symbol:path}", response_model=ResearchReport)
async def get_research_report(
    symbol: str,
    user: UserResponse | None = Depends(get_current_user_or_github_actions),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
    timeframe: str | None = Query(None, description="Optional one-off timeframe override. Preferences remain the default."),
) -> ResearchReport:
    # The S2 default timeframe is intentionally the orchestration default. A
    # future one-off override can be consumed without changing saved settings.
    # The report service currently resolves its primary timeframe from the
    # persisted preferences, so this parameter is reserved for a later request
    # override phase rather than silently changing the algorithm today.
    _ = timeframe
    return await _generate_report(symbol, user, access_token)
