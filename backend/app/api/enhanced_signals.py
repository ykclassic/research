from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user
from app.models.enhanced_signal import EnhancedSignalResponse
from app.models.market import Timeframe
from app.services.entitlement import EntitlementError, require_feature
from app.services.settings_integration import market_coverage, market_data_policy
from app.preferences.service import preferences_service
from app.providers.kraken_public import KrakenPublicProvider
from app.services.quote_service import QuoteService
from app.services.signal_candle_scheduler import SignalCandleScheduler
from app.services.enhanced_signal_engine import generate_enhanced_signal
from app.services.news_research_resilient import news_research
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/enhanced-signals", tags=["enhanced-signals"])

quote_service = QuoteService()
kraken_public = KrakenPublicProvider()
scheduler = SignalCandleScheduler(quote_service, kraken_public)

REQUIRED = (
    Timeframe.DAY_1,
    Timeframe.HOUR_4,
    Timeframe.HOUR_1,
    Timeframe.MINUTE_15,
    Timeframe.MINUTE_5,
)
TIMEOUT_SECONDS = 40.0


def _news_gate_passed(news) -> bool:
    if not news_research.configured:
        return False
    now = datetime.now(timezone.utc)
    for event in news.fundamental_events:
        importance = (event.importance or '').strip().lower()
        high = importance in {'high', 'very high', 'critical', '3', '3.0'}
        if high and now - timedelta(minutes=30) <= event.event_timestamp <= now + timedelta(minutes=60):
            return False
    for item in news.news:
        if item.event_type.value == 'REGULATORY' and item.published_at >= now - timedelta(hours=2):
            return False
    return True


@router.get("/{symbol:path}", response_model=EnhancedSignalResponse)
async def get_enhanced_signal(
    symbol: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    limit: int = Query(250, ge=60, le=5000),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> EnhancedSignalResponse:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authenticated session is required.")
    try:
        entitlement = require_feature(access_token, user.id, "enhanced_signal")
        normalized = normalize_symbol(symbol).internal
        record = preferences_service.get_or_create(access_token, user.id)
        if normalized not in market_coverage(record).enabled_symbols:
            raise HTTPException(status_code=404, detail=f"{normalized} is not enabled in your market-data settings.")
        datasets = await asyncio.wait_for(
            scheduler.get_required_datasets(
                normalized,
                REQUIRED,
                limit,
                market_data_policy(record),
            ),
            timeout=TIMEOUT_SECONDS,
        )
        asset_class = normalize_symbol(normalized).asset_class
        news = await news_research.research(symbol=normalized, days=1, limit=50)
        news_filter_passed = _news_gate_passed(news)
        signal, checks = generate_enhanced_signal(
            datasets,
            asset_class=asset_class,
            news_filter_passed=news_filter_passed,
        )
        return EnhancedSignalResponse(
            signal=signal,
            checks=checks,
            methodology_version="enhanced-smc-v1",
            risk_policy={
                "risk_per_trade": 0.0075,
                "max_daily_loss": 0.02,
                "max_correlated_positions": 2,
                "stop_widening": False,
                "averaging_down": False,
            },
            research_note="Enhanced Signal is a deterministic SMC/price-action research strategy. Confidence is setup quality, not a calibrated probability. Production promotion requires sufficient outcome samples and validation.",
        )
    except HTTPException:
        raise
    except EntitlementError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Enhanced Signal market-data acquisition timed out.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Enhanced Signal is temporarily unavailable: {exc}") from exc
