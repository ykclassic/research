from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.models.news import NewsResearchResponse
from app.services.news_research_resilient import news_research

router = APIRouter(
    prefix="/api/news",
    tags=["news"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)


@router.get("/research", response_model=NewsResearchResponse)
async def get_news_research(
    symbol: str | None = Query(default=None),
    days: int = Query(default=1, ge=1, le=7),
    limit: int = Query(default=25, ge=1, le=50),
) -> NewsResearchResponse:
    try:
        return await news_research.research(symbol=symbol, days=days, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
