from fastapi import APIRouter

from app.services.quote_service import QuoteService

router = APIRouter(prefix="/api/providers", tags=["providers"])
service = QuoteService()


@router.get("/status")
async def provider_status():
    return {"providers": await service.provider_status()}
