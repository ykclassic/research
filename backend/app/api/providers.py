from fastapi import APIRouter

from app.services.quote_service import QuoteService

router = APIRouter(prefix="/api/providers", tags=["providers"])
service = QuoteService()


@router.get("/status")
async def provider_status():
    return {
        "providers": [item.model_dump(mode="json") for item in service.orchestrator.provider_status()]
    }
