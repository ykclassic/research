from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user_or_github_actions
from app.models.market import Timeframe
from app.models.signal import CryptoSignal, CryptoSignalList
from app.preferences.models import default_preferences
from app.preferences.service import preferences_service
from app.providers.kraken_public import KrakenPublicProvider
from app.services. quote_service import QuoteService
from app.services.settings_integration import market_coverage, market_data_policy
from app.services.signal_candle_scheduler import SignalCandleScheduler
from app.services.signal_engine import generate_crypto_signal
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/signals", tags=["signals"])
quote_service = QuoteService()
kraken_public = KrakenPublicProvider()
signal_candle_scheduler = SignalCandleScheduler(quote_service, kraken_public)

REQUIRED_TIMEFRAMES = (
    Timeframe.DAY_1,
    Timeframe.HOUR_4,
    Timeframe.HOUR_1,
    Timeframe.MINUTE_15,
)


def _default_signal_preferences() -> dict[str, object]:
    return dict(default_preferences()["signal_preferences"])


async def _authorized_symbol(
    symbol: str,
    user: UserResponse | None,
    access_token: str | None,
) -> tuple[str, dict[str, object], object | None]:
    mapping = normalize_symbol(symbol)
    if user is None or not access_token:
        return mapping.internal, _default_signal_preferences(), None

    record = preferences_service.get_or_create(access_token, user.id)
    coverage = market_coverage(record)
    if mapping.internal not in coverage.enabled_symbols:
        raise HTTPException(
            status_code=404,
            detail=f"{mapping.internal} is not enabled in your market-data settings.",
        )
    return mapping.internal, dict(record.signal_preferences), record


async def _generate(
    symbol: str,
    limit: int,
    signal_preferences: dict[str, object] | None = None,
    policy=None,
) -> CryptoSignal:
    datasets = await signal_candle_scheduler.get_required_datasets(
        symbol,
        REQUIRED_TIMEFRAMES,
        limit,
        policy,
    )
    preferences = (
        signal_preferences
        if signal_preferences is not None
        else _default_signal_preferences()
    )
    return generate_crypto_signal(datasets, preferences)


@router.get("", response_model=CryptoSignalList)
async def get_crypto_signals(
    limit: int = Query(250, ge=30, le=5000),
    user: Annotated[UserResponse | None, Depends(get_current_user_or_github_actions)] = None,
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> CryptoSignalList:
    """Compatibility endpoint.

    The production UI does not call this collection endpoint. Signal generation
    is intentionally pair-scoped through GET /api/signals/{symbol}; this legacy
    endpoint remains only for older API consumers and test compatibility.
    """
    try:
        signal_preferences = _default_signal_preferences()
        record = None
        if user is not None and access_token:
            record = preferences_service.get_or_create(access_token, user.id)
            signal_preferences = dict(record.signal_preferences)
        policy = market_data_policy(record) if record is not None else None
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Signal preferences are temporarily unavailable."
        ) from exc

    symbols = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
    signals: list[CryptoSignal] = []
    failures: list[str] = []

    for symbol in symbols:
        try:
            signal = await _generate(symbol, limit, signal_preferences, policy)
            if signal.research_eligible:
                signals.append(signal)
        except Exception as exc:
            failures.append(f"{symbol}: {exc}")

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
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
