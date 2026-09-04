from fastapi import APIRouter, Query

from app.services.quote_service import QuoteService

router = APIRouter(prefix="/api/providers", tags=["providers"])
service = QuoteService()


@router.get("/status")
async def provider_status(
    domain: str = Query("quote", pattern="^(quote|candles)$"),
):
    return {
        "domain": domain,
        "providers": [
            item.model_dump(mode="json")
            for item in service.orchestrator.provider_status(domain)  # type: ignore[arg-type]
        ],
    }
