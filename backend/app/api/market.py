from fastapi import APIRouter, HTTPException, Query

from app.models import QuoteStatus
from app.services.quote_service import QuoteService
from app.services.scoring import score_quote

router = APIRouter(prefix="/api/market", tags=["market"])
service = QuoteService()


@router.get("/quote/{symbol:path}")
async def get_quote(symbol: str, refresh: bool = False):
    try:
        quote = await service.get_quote(symbol, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    quotes = []
    for symbol in requested:
        try:
            quotes.append(await service.get_quote(symbol, force_refresh=refresh))
        except ValueError as exc:
            quotes.append({
                "symbol": symbol.upper(),
                "status": QuoteStatus.UNAVAILABLE,
                "error": str(exc),
            })

    return {
        "quotes": [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in quotes
        ]
    }


@router.get("/status")
async def market_status():
    return {
        "quote_provider": service.provider.name,
        "cache_seconds": service.cache.__class__.__name__,
        "configured": await service.provider.health(),
    }


@router.get("/scanner")
async def scanner(
    symbols: str = Query("BTC/USD,ETH/USD,EUR/USD,NVDA,SPY"),
):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    quotes = await service.get_quotes(requested)
    return {"items": [score_quote(quote) | {"quote": quote.model_dump(mode="json")} for quote in quotes]}
