from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.auth import get_current_user_or_github_actions, require_github_actions
from app.models import QuoteStatus
from app.models.market import Timeframe
from app.services.quote_service import QuoteService
from app.services.scoring import score_quote

router = APIRouter(prefix="/api/market", tags=["market"], dependencies=[Depends(get_current_user_or_github_actions)])
service = QuoteService()


def _quality(quote):
    return {
        "validated": quote.status != QuoteStatus.UNAVAILABLE and quote.price is not None,
        "research_eligible": quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED},
        "request_latency_ms": quote.latency_ms,
        "freshness_status": quote.freshness_status,
        "freshness_age_seconds": quote.freshness_age_seconds,
        "error_code": quote.error_code,
        "error": quote.error,
        "provider_credits_used": quote.provider_credits_used,
        "provider_credits_remaining": quote.provider_credits_remaining,
        "candle_completeness": "NOT_APPLICABLE",
        "provenance": {
            "provider": quote.source,
            "provider_symbol": quote.provider_symbol,
            "provider_timestamp": quote.provider_timestamp,
            "observed_at": quote.observed_at,
            "fallback_used": quote.fallback_used,
            "provider_attempts": quote.provider_attempts,
        },
        "cache": {"hit": quote.cache_hit},
    }


@router.get("/quote/{symbol:path}")
async def get_quote(symbol: str, response: Response, refresh: bool = False):
    try:
        quote = await service.get_quote(symbol, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.headers["X-Market-Data-Source"] = quote.source or "unknown"
    response.headers["X-Market-Data-Cache"] = "HIT" if quote.cache_hit else "MISS"
    response.headers["X-Market-Data-Refresh"] = "true" if refresh else "false"
    response.headers["X-Market-Data-Freshness"] = quote.freshness_status.value
    response.headers["X-Market-Data-Fallback"] = "true" if quote.fallback_used else "false"
    response.headers["X-Market-Data-Error-Code"] = quote.error_code.value if quote.error_code else ""
    return {"quote": quote.model_dump(mode="json"), "data_quality": _quality(quote)}


@router.get("/quotes")
async def get_quotes(symbols: str = Query("BTC/USD,ETH/USD,EUR/USD,NVDA,SPY"), refresh: bool = False):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="At least one symbol is required.")
    quotes = await service.get_quotes(requested, force_refresh=refresh)
    return {"quotes": [quote.model_dump(mode="json") for quote in quotes], "data_quality": [_quality(quote) for quote in quotes]}


@router.get("/status")
async def market_status():
    return {"providers": [item.model_dump(mode="json") for item in service.orchestrator.provider_status()], "quote_cache_entries": service.orchestrator.quote_cache.size(), "candle_cache_entries": service.orchestrator.candle_cache.size()}


@router.get("/verification/fallback/{symbol:path}", dependencies=[Depends(require_github_actions)])
async def verify_fallback_path(symbol: str, timeframe: Timeframe = Query(Timeframe.HOUR_1), limit: int = Query(250, ge=50, le=5000)):
    """Protected production failure-injection route.

    Twelve Data is deliberately excluded. The orchestrator must select a configured
    secondary provider or use a previously validated canonical cache entry.
    """
    try:
        quote = await service.orchestrator.get_quote(symbol, force_refresh=True, excluded_providers={"twelve_data"})
        candles = await service.orchestrator.get_candles(symbol, timeframe, limit, excluded_providers={"twelve_data"})
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "quote": quote.model_dump(mode="json"),
        "candles": candles.model_dump(mode="json"),
        "fallback_verified": quote.fallback_used or candles.fallback_used,
        "selected_quote_provider": quote.source,
        "selected_candle_provider": candles.source,
        "provider_attempts": {"quote": quote.provider_attempts, "candles": candles.provider_attempts},
    }


@router.get("/scanner")
async def scanner(symbols: str = Query("BTC/USD,ETH/USD,EUR/USD,NVDA,SPY")):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    quotes = await service.get_quotes(requested)
    return {"items": [score_quote(quote) | {"quote": quote.model_dump(mode="json")} for quote in quotes]}
