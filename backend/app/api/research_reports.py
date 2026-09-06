from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user_or_github_actions
from app.models.research_report import ResearchReport
from app.services.research_history import create_history_record
from app.services.research_report import ResearchReportService
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/research-reports", tags=["research-reports"], dependencies=[Depends(get_current_user_or_github_actions)])
service = ResearchReportService()


@router.get("/{symbol:path}", response_model=ResearchReport)
async def get_research_report(
    symbol: str,
    user: UserResponse | None = Depends(get_current_user_or_github_actions),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> ResearchReport:
    try:
        report = await service.generate(symbol)
        # GitHub OIDC callers validate the report but do not own user history.
        if user is not None and access_token:
            try:
                saved = create_history_record(
                    access_token,
                    user.id,
                    record_type="REPORT",
                    symbol=report.symbol,
                    title=f"{report.symbol} Market Research",
                    payload=report.model_dump(mode="json"),
                )
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
