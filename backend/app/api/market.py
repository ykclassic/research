from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models import QuoteStatus
from app.services.quote_service import QuoteService
from app.services.scoring import score_quote

router = APIRouter(
    prefix="/api/market",
    tags=["market"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)
service = QuoteService()


@router.get("/quote/{symbol:path}")
async def get_quote(symbol: str, response: Response, refresh: bool = False):
    try:
        quote = await service.get_quote(symbol, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response.headers["X-Market-Data-Source"] = quote.source or "unknown"
    response.headers["X-Market-Data-Cache"] = "HIT" if quote.cache_hit else "MISS"
    response.headers["X-Market-Data-Refresh"] = "true" if refresh else "false"
    response.headers["X-Market-Data-Freshness-SLA-Seconds"] = str(
        settings.stale_quote_seconds
    )
    if quote.provider_timestamp is not None and quote.observed_at is not None:
        provider_age_seconds = (
            quote.observed_at - quote.provider_timestamp
        ).total_seconds()
        response.headers["X-Market-Data-Provider-Age-Seconds"] = f"{provider_age_seconds:.3f}"

    return {
        "quote": quote.model_dump(mode="json"),
        "data_quality": {
            "validated": quote.status == QuoteStatus.LIVE,
            "research_eligible": quote.status == QuoteStatus.LIVE,
        },
    }


@router.get("/quotes")
async def get_quotes(
    symbols: str = Query("BTC/USD,ETH/USD,EUR/USD,NVDA,SPY"),
    refresh: bool = False,
):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="At least one symbol is required.")

    try:
        quotes = await service.get_quotes(requested, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "quotes": [quote.model_dump(mode="json") for quote in quotes]
    }


@router.get("/status")
async def market_status():
    return {
        "quote_provider": service.provider.name,
        "cache_seconds": service.cache.__class__.__name__,
        "configured": await service.provider.health(),
        "freshness_sla_seconds": settings.stale_quote_seconds,
    }


@router.get("/scanner")
async def scanner(
    symbols: str = Query("BTC/USD,ETH/USD,EUR/USD,NVDA,SPY"),
):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    quotes = await service.get_quotes(requested)
    return {"items": [score_quote(quote) | {"quote": quote.model_dump(mode="json")} for quote in quotes]}
