from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models.market import OHLCVDataset, Timeframe
from app.models.risk import PositionQualification
from app.services.feature_engine import calculate_feature_set
from app.services.market_structure import analyze_market_structure
from app.services.mtf_analysis import REQUIRED_TIMEFRAMES, analyze_multi_timeframe
from app.services.quote_service import QuoteService
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime
from app.services.risk_management import qualify_position
from app.services.strategy_portfolio import evaluate_strategy_portfolio
from app.services.strategy_selection import select_strategy
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/risk", tags=["risk-management"], dependencies=[Depends(get_current_user_or_github_actions)])
quote_service = QuoteService()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    incomplete = [i for i, candle in enumerate(dataset.candles) if not candle.is_complete]
    if incomplete and incomplete != [len(dataset.candles) - 1]:
        raise ValueError("Provider returned incomplete candles outside the latest candle.")
    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for risk qualification.")
    return dataset.model_copy(update={"candles": completed})


async def _get_dataset(symbol: str, timeframe: Timeframe, limit: int) -> OHLCVDataset:
    dataset = await asyncio.wait_for(quote_service.orchestrator.get_candles(symbol, timeframe, limit), timeout=settings.analysis_timeout_seconds)
    return _completed_dataset(dataset)


@router.get("/{symbol:path}", response_model=PositionQualification)
async def get_risk_qualification(
    symbol: str,
    account_equity: float = Query(..., gt=0),
    limit: int = Query(250, ge=220, le=5000),
) -> PositionQualification:
    """Return a deterministic position candidate; this endpoint never places orders."""
    try:
        mapping = normalize_symbol(symbol)
        datasets_list = await asyncio.gather(*(_get_dataset(mapping.internal, timeframe, limit) for timeframe in REQUIRED_TIMEFRAMES))
        datasets = dict(zip(REQUIRED_TIMEFRAMES, datasets_list))
        structures = {timeframe: analyze_market_structure(datasets[timeframe]).events for timeframe in REQUIRED_TIMEFRAMES}
        mtf = analyze_multi_timeframe(datasets, structures)

        m15 = datasets[Timeframe.MINUTE_15]
        m15_features = calculate_feature_set(m15)
        regime = detect_regime(m15)
        portfolio = evaluate_strategy_portfolio(m15, m15_features, regime)
        selection = select_strategy(portfolio, mtf)

        h1 = datasets[Timeframe.HOUR_1]
        h1_features = calculate_feature_set(h1)
        return qualify_position(selection, h1, h1_features, account_equity)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the risk-qualification latency budget.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
