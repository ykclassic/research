from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models.market import OHLCVDataset, Timeframe
from app.models.mtf import MultiTimeframeResult
from app.services.candle_freshness import require_current_completed_candles
from app.services.market_structure import analyze_market_structure
from app.services.mtf_analysis import MINIMUM_CANDLES, REQUIRED_TIMEFRAMES, analyze_multi_timeframe
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/mtf", tags=["multi-timeframe"], dependencies=[Depends(get_current_user_or_github_actions)])
quote_service = QuoteService()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    incomplete_indexes = [index for index, candle in enumerate(dataset.candles) if not candle.is_complete]
    if incomplete_indexes and incomplete_indexes != [len(dataset.candles) - 1]:
        raise ValueError("Provider returned incomplete candles outside the latest candle.")
    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for multi-timeframe research.")
    return dataset.model_copy(update={"candles": completed})


async def _load(symbol: str, timeframe: Timeframe, limit: int) -> tuple[Timeframe, OHLCVDataset]:
    dataset = await asyncio.wait_for(
        quote_service.orchestrator.get_candles(symbol, timeframe, limit),
        timeout=settings.analysis_timeout_seconds,
    )
    dataset = require_current_completed_candles(dataset)
    return timeframe, _completed_dataset(dataset)


@router.get("/{symbol:path}", response_model=MultiTimeframeResult)
async def get_multi_timeframe_analysis(
    symbol: str,
    limit: int = Query(250, ge=30, le=5000),
) -> MultiTimeframeResult:
    try:
        mapping = normalize_symbol(symbol)
        results = await asyncio.gather(
            *(_load(mapping.internal, timeframe, limit) for timeframe in REQUIRED_TIMEFRAMES),
            return_exceptions=True,
        )
        failures: list[str] = []
        datasets: dict[Timeframe, OHLCVDataset] = {}
        for timeframe, result in zip(REQUIRED_TIMEFRAMES, results):
            if isinstance(result, BaseException):
                failures.append(f"{timeframe.value}: {result}")
            else:
                _, dataset = result
                datasets[timeframe] = dataset
        if failures:
            status = quote_service.orchestrator.provider_status("candles")
            provider_details = "; ".join(
                f"{item.provider}=" + (item.last_error or "no failure recorded")
                for item in status
                if item.configured
            )
            detail = "MTF candle load failed: " + " | ".join(failures)
            if provider_details:
                detail += f". Candle provider health: {provider_details}"
            raise HTTPException(status_code=503, detail=detail)
        structures = {
            timeframe: tuple(analyze_market_structure(dataset).events)
            for timeframe, dataset in datasets.items()
        }
        return analyze_multi_timeframe(datasets, structures)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the multi-timeframe latency budget and no cached dataset was available.") from exc
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
