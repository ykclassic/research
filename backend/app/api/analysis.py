from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.services.quote_service import QuoteService
from app.services.technical_analysis import calculate_indicators
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/analysis", tags=["analysis"], dependencies=[Depends(get_current_user)])
quote_service = QuoteService()

INTERVALS = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}


class CandleResponse(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class AnalysisResponse(BaseModel):
    symbol: str
    timeframe: str
    source: str
    candles: list[CandleResponse]
    indicators: dict[str, float | str | None]


@router.get("/{symbol:path}", response_model=AnalysisResponse)
async def get_analysis(
    symbol: str,
    timeframe: str = Query("1h"),
    limit: int = Query(250, ge=50, le=5000),
):
    if timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe. Choose one of: {', '.join(INTERVALS)}")
    try:
        mapping = normalize_symbol(symbol)
        candles = await quote_service.provider.get_candles(mapping.internal, INTERVALS[timeframe], limit)
        if len(candles) < 20:
            raise HTTPException(status_code=503, detail="Insufficient historical candles for technical analysis.")
        indicators = calculate_indicators(candles)
        return AnalysisResponse(
            symbol=mapping.internal,
            timeframe=timeframe,
            source=quote_service.provider.name,
            candles=[CandleResponse(**c.__dict__) for c in candles],
            indicators=indicators,
        )
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
