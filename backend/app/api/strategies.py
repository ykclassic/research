from __future__ import annotations

import asyncio

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user_or_github_actions
from app.config import settings
from app.models.market import OHLCVDataset, Timeframe
from app.models.strategy import StrategyPortfolioResult
from app.services.entitlement import FeatureNotEntitledError, require_feature
from app.services.feature_engine import calculate_feature_set
from app.services.quote_service import QuoteService
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime
from app.services.strategy_portfolio import evaluate_strategy_portfolio
from app.symbols import normalize_symbol

router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)
quote_service = QuoteService()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    incomplete_indexes = [
        index for index, candle in enumerate(dataset.candles) if not candle.is_complete
    ]
    if incomplete_indexes and incomplete_indexes != [len(dataset.candles) - 1]:
        raise ValueError("Provider returned incomplete candles outside the latest candle.")

    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(
            f"At least {MINIMUM_CANDLES} completed candles are required for strategy evaluation."
        )
    return dataset.model_copy(update={"candles": completed})


@router.get("/{symbol:path}", response_model=StrategyPortfolioResult)
async def get_strategy_portfolio(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=220, le=5000),
    user: UserResponse | None = Depends(get_current_user_or_github_actions),
    access_token: str | None = Cookie(None, alias="mr_access_token"),
) -> StrategyPortfolioResult:
    if user is None or not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        require_feature(access_token, user.id, "backtesting")
        mapping = normalize_symbol(symbol)
        dataset = await asyncio.wait_for(
            quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )
        completed_dataset = _completed_dataset(dataset)
        features = calculate_feature_set(completed_dataset)
        regime = detect_regime(completed_dataset)
        result = evaluate_strategy_portfolio(completed_dataset, features, regime)
        return result
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail="Market-data providers exceeded the strategy evaluation latency budget.",
        ) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
