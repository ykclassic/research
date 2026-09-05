from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user_or_github_actions
from app.config import settings
from app.models.market import OHLCVDataset, Timeframe
from app.models.mtf import MultiTimeframeResult
from app.providers.kraken_public import KrakenPublicProvider
from app.services.candle_freshness import require_current_completed_candles
from app.services.candle_persistence import load_dataset as load_persisted_dataset
from app.services.candle_persistence import save_dataset as save_persisted_dataset
from app.services.market_structure import analyze_market_structure
from app.services.mtf_analysis import MINIMUM_CANDLES, REQUIRED_TIMEFRAMES, analyze_multi_timeframe
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/mtf", tags=["multi-timeframe"])
quote_service = QuoteService()
kraken_public = KrakenPublicProvider()


def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
    incomplete_indexes = [index for index, candle in enumerate(dataset.candles) if not candle.is_complete]
    if incomplete_indexes and incomplete_indexes != [len(dataset.candles) - 1]:
        raise ValueError("Provider returned incomplete candles outside the latest candle.")
    completed = dataset.completed_candles
    if len(completed) < MINIMUM_CANDLES:
        raise ValueError(f"At least {MINIMUM_CANDLES} completed candles are required for multi-timeframe research.")
    return dataset.model_copy(update={"candles": completed})


async def _load(
    symbol: str,
    timeframe: Timeframe,
    limit: int,
    *,
    user: UserResponse | None,
    access_token: str | None,
) -> tuple[Timeframe, OHLCVDataset]:
    if user is not None and access_token:
        persisted = await asyncio.to_thread(
            load_persisted_dataset,
            access_token,
            user.id,
            symbol,
            timeframe,
        )
        if persisted is not None:
            # Persisted data is only a performance cache. It must still satisfy
            # the same current-completed-candle contract as live provider data.
            current = require_current_completed_candles(persisted)
            current = _completed_dataset(current)
            return timeframe, current.model_copy(update={"cache_hit": True, "fallback_used": True, "request_latency_ms": 0})

    mapping = normalize_symbol(symbol)
    dataset: OHLCVDataset
    if mapping.asset_class == "crypto":
        try:
            # Phase 7 crypto analysis must not depend on quota-limited paid
            # providers. Kraken's public OHLC endpoint supports the exact
            # Daily/H4/H1/M15 hierarchy without credentials.
            dataset = await asyncio.wait_for(
                kraken_public.get_candles(symbol, timeframe, limit),
                timeout=settings.analysis_timeout_seconds,
            )
        except Exception as primary_exc:
            # Preserve the existing provider orchestrator as a secondary
            # fallback for deployments where Kraken is temporarily unavailable.
            try:
                dataset = await asyncio.wait_for(
                    quote_service.orchestrator.get_candles(symbol, timeframe, limit),
                    timeout=settings.analysis_timeout_seconds,
                )
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Primary crypto candle provider failed: {primary_exc}; "
                    f"orchestrated fallback failed: {fallback_exc}"
                ) from fallback_exc
    else:
        dataset = await asyncio.wait_for(
            quote_service.orchestrator.get_candles(symbol, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )

    dataset = require_current_completed_candles(dataset)
    dataset = _completed_dataset(dataset)
    if user is not None and access_token:
        await asyncio.to_thread(save_persisted_dataset, access_token, user.id, dataset)
    return timeframe, dataset


@router.get("/{symbol:path}", response_model=MultiTimeframeResult)
async def get_multi_timeframe_analysis(
    symbol: str,
    limit: int = Query(250, ge=30, le=5000),
    user: Annotated[UserResponse | None, Depends(get_current_user_or_github_actions)] = None,
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> MultiTimeframeResult:
    try:
        mapping = normalize_symbol(symbol)
        results = await asyncio.gather(
            *(_load(mapping.internal, timeframe, limit, user=user, access_token=access_token) for timeframe in REQUIRED_TIMEFRAMES),
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
