from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.market import router as market_router
from app.api.providers import router as providers_router
from app.api.watchlists import router as watchlists_router
from app.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="Adaptive Intelligent Market Research Bot API",
    version="1.3.0",
    lifespan=lifespan,
)

origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    expose_headers=["X-CSRF-Token"],
)

app.include_router(auth_router)
app.include_router(market_router)
app.include_router(providers_router)
app.include_router(watchlists_router)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "adaptive-market-research-bot",
        "environment": settings.app_env,
    }
