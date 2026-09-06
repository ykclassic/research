from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.models.research_report import ResearchReport
from app.services.research_report import ResearchReportService

router = APIRouter(prefix="/api/research-reports", tags=["research-reports"], dependencies=[Depends(get_current_user_or_github_actions)])
service = ResearchReportService()


@router.get("/{symbol:path}", response_model=ResearchReport)
async def get_research_report(
    symbol: str,
) -> ResearchReport:
    try:
        return await service.generate(symbol)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the research-report latency budget.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
