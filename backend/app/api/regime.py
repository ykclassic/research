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

router = APIRouter(
    prefix="/api/regime",
    tags=["regime"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)

quote_service = QuoteService()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    """Prepare provider candles for regime analysis without admitting a forming candle.

    Market-data endpoints may legitimately return the currently forming candle.
    Regime detection, however, is a completed-candle-only contract. The API layer
    therefore removes only a trailing forming candle and rejects an incomplete
    candle appearing anywhere else in the provider series.
    """
    incomplete_indexes = [
        index
        for index, candle in enumerate(dataset.candles)
        if not candle.is_complete
    ]
    if incomplete_indexes:
        last_index = len(dataset.candles) - 1
        if incomplete_indexes != [last_index]:
            raise ValueError(
                "Provider returned incomplete candles outside the latest candle."
            )

    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(
            f"At least {MINIMUM_CANDLES} completed candles are required for regime detection."
        )

    return dataset.model_copy(update={"candles": completed})


@router.get("/{symbol:path}", response_model=MarketRegimeResult)
async def get_regime(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=220, le=5000),
) -> MarketRegimeResult:
    """Return deterministic market regime evidence from completed provider candles."""
    try:
        mapping = normalize_symbol(symbol)
        dataset = await asyncio.wait_for(
            quote_service.provider.get_candles(mapping.internal, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )
        return detect_regime(_completed_dataset(dataset))
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail="Market-data provider exceeded the regime latency budget.",
        ) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
