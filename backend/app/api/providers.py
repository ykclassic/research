from fastapi import APIRouter

from app.services.quote_service import QuoteService

router = APIRouter(prefix="/api/providers", tags=["providers"])
service = QuoteService()


@router.get("/status")
async def provider_status():
    configured = await service.provider.health()
    return {
        "providers": [
            {
                "provider": service.provider.name,
                "configured": configured,
                "reachable": configured,
                "message": (
                    "Configured; live requests are available."
                    if configured
                    else "Not configured. Add TWELVE_DATA_API_KEY to the backend environment."
                ),
            }
        ]
    }
