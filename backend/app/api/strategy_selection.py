from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models.market import OHLCVDataset, Timeframe
from app.models.strategy_selection import StrategySelectionResult
from app.services.feature_engine import calculate_feature_set
from app.services.market_structure import analyze_market_structure
from app.services.mtf_analysis import REQUIRED_TIMEFRAMES, analyze_multi_timeframe
from app.services.quote_service import QuoteService
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime
from app.services.strategy_portfolio import evaluate_strategy_portfolio
from app.services.strategy_selection import select_strategy
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/strategy-selection", tags=["strategy-selection"], dependencies=[Depends(get_current_user_or_github_actions)])
quote_service = QuoteService()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    incomplete = [i for i, candle in enumerate(dataset.candles) if not candle.is_complete]
    if incomplete and incomplete != [len(dataset.candles) - 1]:
        raise ValueError("Provider returned incomplete candles outside the latest candle.")
    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for strategy qualification.")
    return dataset.model_copy(update={"candles": completed})


async def _get_dataset(symbol: str, timeframe: Timeframe, limit: int) -> OHLCVDataset:
    dataset = await asyncio.wait_for(quote_service.orchestrator.get_candles(symbol, timeframe, limit), timeout=settings.analysis_timeout_seconds)
    return _completed_dataset(dataset)


@router.get("/{symbol:path}", response_model=StrategySelectionResult)
async def get_strategy_selection(symbol: str, limit: int = Query(250, ge=220, le=5000)) -> StrategySelectionResult:
    try:
        mapping = normalize_symbol(symbol)
        datasets_list = await asyncio.gather(*(_get_dataset(mapping.internal, timeframe, limit) for timeframe in REQUIRED_TIMEFRAMES))
        datasets = dict(zip(REQUIRED_TIMEFRAMES, datasets_list))
        structures = {timeframe: analyze_market_structure(datasets[timeframe]).events for timeframe in REQUIRED_TIMEFRAMES}
        mtf = analyze_multi_timeframe(datasets, structures)
        m15 = datasets[Timeframe.MINUTE_15]
        features = calculate_feature_set(m15)
        regime = detect_regime(m15)
        portfolio = evaluate_strategy_portfolio(m15, features, regime)
        return select_strategy(portfolio, mtf)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the strategy-selection latency budget.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
