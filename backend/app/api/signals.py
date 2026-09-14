from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user_or_github_actions
from app.config import settings
from app.models.market import OHLCVDataset, Timeframe
from app.models.signal import CryptoSignal, CryptoSignalList
from app.preferences.models import default_preferences
from app.preferences.service import preferences_service
from app.providers.kraken_public import KrakenPublicProvider
from app.services.candle_freshness import require_current_completed_candles
from app.services.quote_service import QuoteService
from app.services.settings_integration import market_data_policy, validate_dataset_policy
from app.services.signal_engine import generate_crypto_signal
from app.symbols import SYMBOLS, normalize_symbol

router = APIRouter(prefix="/api/signals", tags=["signals"])
quote_service = QuoteService()
kraken_public = KrakenPublicProvider()
CRYPTO_SYMBOLS = tuple(symbol for symbol, mapping in SYMBOLS.items() if mapping.asset_class == "crypto")
REQUIRED_TIMEFRAMES = (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15)


async def _load_crypto_dataset(symbol: str, timeframe: Timeframe, limit: int, policy=None) -> OHLCVDataset:
    try:
        dataset = await asyncio.wait_for(
            kraken_public.get_candles(symbol, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )
    except Exception as primary_exc:
        try:
            dataset = await asyncio.wait_for(
                quote_service.orchestrator.get_candles(symbol, timeframe, limit),
                timeout=settings.analysis_timeout_seconds,
            )
        except Exception as fallback_exc:
            raise RuntimeError(
                f"{symbol} {timeframe.value}: primary crypto provider failed ({primary_exc}); fallback failed ({fallback_exc})"
            ) from fallback_exc
    if policy is not None:
        validate_dataset_policy(dataset, policy)
    return require_current_completed_candles(dataset)


def _default_signal_preferences() -> dict[str, object]:
    return dict(default_preferences()["signal_preferences"])


def _resolve_signal_preferences(user: UserResponse | None, access_token: str | None) -> tuple[dict[str, object], object | None]:
    if user is None or not access_token:
        return _default_signal_preferences(), None
    record = preferences_service.get_or_create(access_token, user.id)
    return dict(record.signal_preferences), record


async def _generate(
    symbol: str,
    limit: int,
    signal_preferences: dict[str, object] | None = None,
    policy=None,
) -> CryptoSignal:
    mapping = normalize_symbol(symbol)
    if mapping.asset_class != "crypto":
        raise ValueError("Signals are currently available for crypto pairs only.")
    results = await asyncio.gather(
        *(_load_crypto_dataset(mapping.internal, timeframe, limit, policy) for timeframe in REQUIRED_TIMEFRAMES),
        return_exceptions=True,
    )
    failures = [
        f"{timeframe.value}: {result}"
        for timeframe, result in zip(REQUIRED_TIMEFRAMES, results)
        if isinstance(result, BaseException)
    ]
    if failures:
        raise RuntimeError("Signal candle load failed: " + " | ".join(failures))
    datasets = {
        timeframe: result
        for timeframe, result in zip(REQUIRED_TIMEFRAMES, results)
        if isinstance(result, OHLCVDataset)
    }
    preferences = signal_preferences if signal_preferences is not None else _default_signal_preferences()
    return generate_crypto_signal(datasets, preferences)


@router.get("", response_model=CryptoSignalList)
async def get_crypto_signals(
    limit: int = Query(250, ge=30, le=5000),
    user: Annotated[UserResponse | None, Depends(get_current_user_or_github_actions)] = None,
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> CryptoSignalList:
    try:
        signal_preferences, record = _resolve_signal_preferences(user, access_token)
        policy = market_data_policy(record)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Signal preferences are temporarily unavailable.") from exc
    results = await asyncio.gather(
        *(_generate(symbol, limit, signal_preferences, policy) for symbol in CRYPTO_SYMBOLS),
        return_exceptions=True,
    )
    signals = [result for result in results if isinstance(result, CryptoSignal) and result.research_eligible]
    failures = [str(result) for result in results if isinstance(result, BaseException)]
    if not signals:
        detail = "No crypto signals currently meet your signal preferences."
        if failures:
            detail += " " + " | ".join(failures)
        raise HTTPException(status_code=503, detail=detail)
    return CryptoSignalList(calculated_at=datetime.now(timezone.utc), signals=tuple(signals))


@router.get("/{symbol:path}", response_model=CryptoSignal)
async def get_crypto_signal(
    symbol: str,
    limit: int = Query(250, ge=30, le=5000),
    user: Annotated[UserResponse | None, Depends(get_current_user_or_github_actions)] = None,
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> CryptoSignal:
    try:
        signal_preferences, record = _resolve_signal_preferences(user, access_token)
        signal = await _generate(symbol, limit, signal_preferences, market_data_policy(record))
        if not signal.research_eligible:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "Signal does not meet the configured preferences.",
                    "reasons": signal.qualification_reasons,
                },
            )
        return signal
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
