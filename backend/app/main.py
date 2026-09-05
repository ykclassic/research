import os
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.ai_research import router as ai_research_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.execution import router as execution_router
from app.api.market import router as market_router
from app.api.market_structure import router as market_structure_router
from app.api.mtf import router as mtf_router
from app.api.performance import router as performance_router
from app.api.providers import router as providers_router
from app.api.regime import router as regime_router
from app.api.risk_management import router as risk_management_router
from app.api.signals import router as signals_router
from app.api.strategies import router as strategies_router
from app.api.strategy_selection import router as strategy_selection_router
from app.api.watchlists import router as watchlists_router
from app.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="Adaptive Intelligent Market Research Bot API", version="1.13.0", lifespan=lifespan)
origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
trusted_hosts = [item.strip() for item in settings.trusted_hosts.split(",") if item.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts or ["localhost", "127.0.0.1", "testserver"])
app.add_middleware(CORSMiddleware, allow_origins=origins or ["http://localhost:5173"], allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "X-CSRF-Token"], expose_headers=["X-CSRF-Token"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Server-Timing"] = f"app;dur={(perf_counter() - started) * 1000:.2f}"
    deployment_commit = os.getenv("RENDER_GIT_COMMIT")
    if deployment_commit:
        response.headers["X-Deployment-Commit"] = deployment_commit
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if settings.app_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(auth_router)
app.include_router(market_router)
app.include_router(providers_router)
app.include_router(watchlists_router)
app.include_router(analysis_router)
app.include_router(regime_router)
app.include_router(strategies_router)
app.include_router(strategy_selection_router)
app.include_router(risk_management_router)
app.include_router(signals_router)
app.include_router(market_structure_router)
app.include_router(mtf_router)
app.include_router(ai_research_router)
app.include_router(execution_router)
app.include_router(performance_router)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "adaptive-market-research-bot",
        "environment": settings.app_env,
        "deployment_commit": os.getenv("RENDER_GIT_COMMIT"),
        "deployment_branch": os.getenv("RENDER_GIT_BRANCH"),
        "deployment_repository": os.getenv("RENDER_GIT_REPO_SLUG"),
    }
