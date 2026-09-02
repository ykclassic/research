from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models import Timeframe
from app.models.market import OHLCVDataset
from app.models.market_structure import MarketStructureResult
from app.services.market_structure import analyze_market_structure
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol

MINIMUM_CANDLES = 30

router = APIRouter(
    prefix="/api/market-structure",
    tags=["market-structure"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)
quote_service = QuoteService()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    incomplete_indexes = [i for i, candle in enumerate(dataset.candles) if not candle.is_complete]
    if incomplete_indexes and incomplete_indexes != [len(dataset.candles) - 1]:
        raise ValueError("Provider returned incomplete candles outside the latest candle.")
    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for market-structure research.")
    return dataset.model_copy(update={"candles": completed})


@router.get("/{symbol:path}", response_model=MarketStructureResult)
async def get_market_structure(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=30, le=5000),
) -> MarketStructureResult:
    try:
        mapping = normalize_symbol(symbol)
        dataset = await asyncio.wait_for(
            quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )
        completed_dataset = _completed_dataset(dataset)
        return analyze_market_structure(completed_dataset)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the market-structure latency budget and no cached dataset was available.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
