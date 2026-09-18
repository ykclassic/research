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
from app.services.settings_integration import market_coverage, market_data_policy, validate_dataset_policy
from app.services.signal_engine import generate_crypto_signal
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/signals", tags=["signals"])
quote_service = QuoteService()
kraken_public = KrakenPublicProvider()
REQUIRED_TIMEFRAMES = (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15)


async def _load_dataset(symbol: str, timeframe: Timeframe, limit: int, policy=None) -> OHLCVDataset:
    mapping = normalize_symbol(symbol)

    # Kraken is credential-free and supports the crypto candle path. Other asset
    # classes use the canonical multi-provider orchestrator.
    if mapping.asset_class == "crypto":
        try:
            dataset = await asyncio.wait_for(
                kraken_public.get_candles(mapping.internal, timeframe, limit),
                timeout=settings.analysis_timeout_seconds,
            )
        except Exception as primary_exc:
            try:
                dataset = await asyncio.wait_for(
                    quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit),
                    timeout=settings.analysis_timeout_seconds,
                )
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"{mapping.internal} {timeframe.value}: primary crypto provider failed "
                    f"({primary_exc}); fallback failed ({fallback_exc})"
                ) from fallback_exc
    else:
        dataset = await asyncio.wait_for(
            quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit),
            timeout=settings.analysis_timeout_seconds,
        )

    if policy is not None:
        validate_dataset_policy(dataset, policy)
    return require_current_completed_candles(dataset)


def _default_signal_preferences() -> dict[str, object]:
    return dict(default_preferences()["signal_preferences"])


def _resolve_signal_preferences(
    user: UserResponse | None, access_token: str | None
) -> tuple[dict[str, object], object | None]:
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
    results = await asyncio.gather(
        *(_load_dataset(mapping.internal, timeframe, limit, policy) for timeframe in REQUIRED_TIMEFRAMES),
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
    preferences = (
        signal_preferences
        if signal_preferences is not None
        else _default_signal_preferences()
    )
    return generate_crypto_signal(datasets, preferences)


async def _authorized_symbol(
    symbol: str,
    user: UserResponse | None,
    access_token: str | None,
) -> tuple[str, dict[str, object], object | None]:
    mapping = normalize_symbol(symbol)
    if user is None or not access_token:
        # Preserve the GitHub Actions verifier path while keeping normal users
        # subject to their saved market-coverage settings.
        return mapping.internal, _default_signal_preferences(), None

    record = preferences_service.get_or_create(access_token, user.id)
    coverage = market_coverage(record)
    if mapping.internal not in coverage.enabled_symbols:
        raise HTTPException(
            status_code=404,
            detail=f"{mapping.internal} is not enabled in your market-data settings.",
        )
    return mapping.internal, dict(record.signal_preferences), record


@router.get("", response_model=CryptoSignalList)
async def get_crypto_signals(
    limit: int = Query(250, ge=30, le=5000),
    user: Annotated[UserResponse | None, Depends(get_current_user_or_github_actions)] = None,
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> CryptoSignalList:
    """Legacy collection endpoint.

    The UI intentionally does not call this endpoint because generating every
    signal is expensive. It remains available for the existing crypto-only API
    contract and tests.
    """
    try:
        signal_preferences, record = _resolve_signal_preferences(user, access_token)
        policy = market_data_policy(record) if record is not None else None
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Signal preferences are temporarily unavailable."
        ) from exc

    # Keep the historical small crypto collection bounded.
    symbols = ("BTC/USDT", "ETH/USDT", "SOL/USDT")

    async def generate_for_symbol(symbol: str) -> CryptoSignal:
        return await _generate(symbol, limit, signal_preferences, policy)

    results = await asyncio.gather(
        *(generate_for_symbol(symbol) for symbol in symbols),
        return_exceptions=True,
    )
    signals = [
        result
        for result in results
        if isinstance(result, CryptoSignal) and result.research_eligible
    ]
    failures = [str(result) for result in results if isinstance(result, BaseException)]
    if not signals:
        detail = "No crypto signals currently meet your signal preferences."
        if failures:
            detail += " " + " | ".join(failures)
        raise HTTPException(status_code=503, detail=detail)
    return CryptoSignalList(
        calculated_at=datetime.now(timezone.utc),
        signals=tuple(signals),
    )


@router.get("/{symbol:path}", response_model=CryptoSignal)
async def get_crypto_signal(
    symbol: str,
    limit: int = Query(250, ge=30, le=5000),
    user: Annotated[UserResponse | None, Depends(get_current_user_or_github_actions)] = None,
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> CryptoSignal:
    try:
        normalized, signal_preferences, record = await _authorized_symbol(
            symbol, user, access_token
        )
        signal = await _generate(
            normalized,
            limit,
            signal_preferences,
            market_data_policy(record) if record is not None else None,
        )
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
        raise HTTPException(status_code=503, detail=str(exc))
