from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models import Timeframe
from app.models.market import OHLCVDataset
from app.models.regime import MarketRegimeResult
from app.services.quote_service import QuoteService
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/regime", tags=["regime"], dependencies=[Depends(get_current_user_or_github_actions)])
quote_service = QuoteService()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    incomplete_indexes = [index for index, candle in enumerate(dataset.candles) if not candle.is_complete]
    if incomplete_indexes:
        last_index = len(dataset.candles) - 1
        if incomplete_indexes != [last_index]:
            raise ValueError("Provider returned incomplete candles outside the latest candle.")
    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for regime detection.")
    return dataset.model_copy(update={"candles": completed})


@router.get("/{symbol:path}", response_model=MarketRegimeResult)
async def get_regime(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=220, le=5000),
) -> MarketRegimeResult:
    try:
        mapping = normalize_symbol(symbol)
        dataset = await asyncio.wait_for(
            quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )
        completed_dataset = _completed_dataset(dataset)
        result = detect_regime(completed_dataset)
        return result.model_copy(update={
            "request_latency_ms": dataset.request_latency_ms,
            "freshness_status": dataset.freshness_status,
            "freshness_age_seconds": dataset.freshness_age_seconds,
            "completeness_status": dataset.completeness_status,
            "fallback_used": dataset.fallback_used,
            "provider_attempts": dataset.provider_attempts,
            "cache_hit": dataset.cache_hit,
        })
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the regime latency budget and no cached regime dataset was available.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
