from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.market import router as market_router
from app.api.providers import router as providers_router
from app.config import settings

app = FastAPI(
    title="Adaptive Intelligent Market Research Bot API",
    version="1.0.0",
)

origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router)
app.include_router(providers_router)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "adaptive-market-research-bot",
        "environment": settings.app_env,
    }
