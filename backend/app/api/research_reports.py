from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException

from app.api.auth import UserResponse, get_current_user_or_github_actions
from app.models.research_report import ResearchReport
from app.preferences.models import UserPreferencesRecord
from app.preferences.service import preferences_service
from app.services.research_history import create_history_record
from app.services.research_preferences import resolve_research_preferences
from app.services.research_report import ResearchReportService
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/research-reports", tags=["research-reports"], dependencies=[Depends(get_current_user_or_github_actions)])
service = ResearchReportService()


def _load_preferences(
    user: UserResponse | None,
    access_token: str | None,
) -> UserPreferencesRecord | None:
    if user is None or not access_token:
        return None
    return preferences_service.get_or_create(access_token, user.id)


async def _generate_report(
    symbol: str | None,
    user: UserResponse | None,
    access_token: str | None,
) -> ResearchReport:
    try:
        preference_record = _load_preferences(user, access_token)
        configuration = resolve_research_preferences(preference_record)
        report = await service.generate(symbol, configuration=configuration)

        # GitHub OIDC callers validate the report but do not own user history.
        if user is not None and access_token and preference_record is not None:
            try:
                privacy = preference_record.privacy_preferences
                if privacy.get("save_generated_reports", True):
                    saved = create_history_record(
                        access_token,
                        user.id,
                        record_type="REPORT",
                        symbol=report.symbol,
                        title=f"{report.symbol} Market Research",
                        payload=report.model_dump(mode="json"),
                    )
                    if privacy.get("save_search_history", True):
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
) -> ResearchReport:
    return await _generate_report(symbol, user, access_token)
