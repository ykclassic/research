import os
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.ai_research import router as ai_research_router
from app.api.alerts import router as alerts_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.execution import router as execution_router
from app.api.market import router as market_router
from app.api.market_session import router as market_session_router
from app.api.market_structure import router as market_structure_router
from app.api.mtf import router as mtf_router
from app.api.news import router as news_router
from app.api.performance import router as performance_router
from app.api.portfolio import router as portfolio_router
from app.api.providers import router as providers_router
from app.api.regime import router as regime_router
from app.api.research_history import router as research_history_router
from app.api.research_reports import router as research_reports_router
from app.api.risk_management import router as risk_management_router
from app.api.signals import router as signals_router
from app.api.signal_outcomes import router as signal_outcomes_router
from app.api.strategies import router as strategies_router
from app.api.strategy_selection import router as strategy_selection_router
from app.api.watchlists import router as watchlists_router
from app.config import settings
from app.preferences.router import router as preferences_router
from app.security import VERCEL_ORIGIN_REGEX
from app.services.system_status import APPLICATION_VERSION


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="Adaptive Intelligent Market Research Bot API",
    version=APPLICATION_VERSION,
    lifespan=lifespan,
)
origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
trusted_hosts = [item.strip() for item in settings.trusted_hosts.split(",") if item.strip()]

# Vercel creates a new HTTPS origin for each production/preview deployment and
# branch URL. Keep the explicit CORS allow-list for fixed origins, while also
# allowing only this project's Vercel hostname family. This is required because
# browser credentials cannot use a wildcard CORS origin.
vercel_origin_regex = VERCEL_ORIGIN_REGEX

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=trusted_hosts or ["localhost", "127.0.0.1", "testserver"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173"],
    allow_origin_regex=vercel_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    expose_headers=["X-CSRF-Token"],
)


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
app.include_router(preferences_router)
app.include_router(market_router)
app.include_router(market_session_router)
app.include_router(providers_router)
app.include_router(watchlists_router)
app.include_router(analysis_router)
app.include_router(regime_router)
app.include_router(strategies_router)
app.include_router(strategy_selection_router)
app.include_router(risk_management_router)
app.include_router(signals_router)
app.include_router(signal_outcomes_router)
app.include_router(market_structure_router)
app.include_router(mtf_router)
app.include_router(news_router)
app.include_router(ai_research_router)
app.include_router(research_reports_router)
app.include_router(research_history_router)
app.include_router(alerts_router)
app.include_router(execution_router)
app.include_router(performance_router)
app.include_router(portfolio_router)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "adaptive-market-research-bot",
        "environment": settings.app_env,
        "application_version": APPLICATION_VERSION,
        "deployment_commit": os.getenv("RENDER_GIT_COMMIT"),
        "deployment_branch": os.getenv("RENDER_GIT_BRANCH"),
        "deployment_repository": os.getenv("RENDER_GIT_REPO_SLUG"),
    }
