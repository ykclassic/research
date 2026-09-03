from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.trade_lifecycle import PerformanceSummary, TradeOutcome
from app.services.performance import close_trade, summarize_performance

router = APIRouter(prefix="/api/performance", tags=["performance"])


class CloseTradeRequest(BaseModel):
    trade: TradeOutcome
    exit_price: float
    exit_time: str
    reason: str


@router.post("/close", response_model=TradeOutcome)
async def close_trade_endpoint(request: CloseTradeRequest) -> TradeOutcome:
    from datetime import datetime
    from app.models.trade_lifecycle import ExitReason

    try:
        return close_trade(
            request.trade,
            request.exit_price,
            datetime.fromisoformat(request.exit_time),
            ExitReason(request.reason),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/summary", response_model=tuple[PerformanceSummary, ...])
async def performance_summary(trades: list[TradeOutcome]) -> tuple[PerformanceSummary, ...]:
    return summarize_performance(trades)
