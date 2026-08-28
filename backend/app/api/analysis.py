from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, model_validator

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models.market import Timeframe
from app.services.feature_engine import calculate_feature_set
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol

router = APIRouter(
    prefix="/api/analysis",
    tags=["analysis"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)
quote_service = QuoteService()


class CandleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @model_validator(mode="after")
    def validate_timestamp_consistency(self) -> AnalysisResponse:
        completed = [candle for candle in self.candles if candle.is_complete]
        if not completed:
            raise ValueError("Analysis response must contain at least one completed candle.")

        expected_latest = completed[-1].timestamp
        if self.latest_candle_timestamp != expected_latest:
            raise ValueError(
                "Analysis latest_candle_timestamp must equal the latest completed candle timestamp."
            )

        if self.candle_count != len(completed):
            raise ValueError(
                "Analysis candle_count must equal the number of completed candles."
            )

        return self


@router.get("/{symbol:path}", response_model=AnalysisResponse)
async def get_analysis(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=50, le=5000),
):
    try:
        mapping = normalize_symbol(symbol)
        dataset = await asyncio.wait_for(
            quote_service.provider.get_candles(
                mapping.internal,
                timeframe,
                limit,
            ),
            timeout=settings.analysis_timeout_seconds,
        )
        result = calculate_feature_set(dataset)
        candles = [CandleResponse.model_validate(candle) for candle in dataset.candles]
        completed = [candle for candle in candles if candle.is_complete]
        if not completed:
            raise ValueError("Provider returned no completed candles for analysis.")

        latest_completed_timestamp = completed[-1].timestamp
        candle_count = len(completed)

        return AnalysisResponse(
            symbol=result.symbol,
            timeframe=result.timeframe,
            source=result.source,
            calculated_at=result.calculated_at,
            latest_candle_timestamp=latest_completed_timestamp,
            candle_count=candle_count,
            candles=candles,
            indicators=result.indicators,
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail="Market-data provider exceeded the analysis latency budget.",
        ) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
