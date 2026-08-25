from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.models.market import Timeframe
from app.services.feature_engine import calculate_feature_set
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol

router = APIRouter(
    prefix="/api/analysis",
    tags=["analysis"],
    dependencies=[Depends(get_current_user)],
)
quote_service = QuoteService()


class CandleResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    is_complete: bool


class AnalysisResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    latest_candle_timestamp: datetime
    candle_count: int
    candles: list[CandleResponse]
    indicators: dict[str, float | str | None]


@router.get("/{symbol:path}", response_model=AnalysisResponse)
async def get_analysis(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=50, le=5000),
):
    try:
        mapping = normalize_symbol(symbol)
        dataset = await quote_service.provider.get_candles(
            mapping.internal,
            timeframe,
            limit,
        )
        result = calculate_feature_set(dataset)
        return AnalysisResponse(
            symbol=result.symbol,
            timeframe=result.timeframe,
            source=result.source,
            calculated_at=result.calculated_at,
            latest_candle_timestamp=result.latest_candle_timestamp,
            candle_count=result.candle_count,
            candles=[CandleResponse.model_validate(candle) for candle in dataset.candles],
            indicators=result.indicators,
        )
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
