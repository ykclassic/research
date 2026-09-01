from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models import Timeframe
from app.models.regime import MarketRegimeResult
from app.services.quote_service import QuoteService
from app.services.regime_detection import detect_regime
from app.symbols import normalize_symbol

router = APIRouter(
    prefix="/api/regime",
    tags=["regime"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)

quote_service = QuoteService()


@router.get("/{symbol:path}", response_model=MarketRegimeResult)
async def get_regime(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=220, le=5000),
) -> MarketRegimeResult:
    """Return deterministic market regime evidence from provider candles."""
    try:
        mapping = normalize_symbol(symbol)
        dataset = await asyncio.wait_for(
            quote_service.provider.get_candles(mapping.internal, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )
        return detect_regime(dataset)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data provider exceeded the regime latency budget.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
