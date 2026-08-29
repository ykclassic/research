from fastapi import APIRouter

from app.services.quote_service import QuoteService

router = APIRouter(prefix="/api/providers", tags=["providers"])
service = QuoteService()


@router.get("/status")
async def provider_status():
    providers = await service.provider_status()
    for provider in providers:
        provider["reachable"] = None
        provider["message"] = "Configured; reachability is verified by an actual provider request." if provider["configured"] else "Not configured."
    return {"providers": providers}
