from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.analysis import quote_service
from app.api.auth import _csrf_token, _require_csrf, get_current_user
from app.config import Settings, settings
from app.main import app
from app.models.market import Candle, OHLCVDataset, Timeframe
from app.services.feature_engine import FeatureEngine


USER = {"id": "u1", "email": "user@example.com"}


def make_dataset(count: int = 40) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(hours=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0 + index,
            symbol="BTC/USD",
            timeframe=Timeframe.HOUR_1,
            source="test_provider",
            is_complete=True,
        )
        for index in range(count)
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test_provider",
        requested_at=start,
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
    )


@pytest.fixture()
def authenticated_client():
    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


def test_health_contract():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["service"] == "adaptive-market-research-bot"
    assert body["environment"]


def test_security_headers_are_present():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["x-permitted-cross-domain-policies"] == "none"


def test_api_responses_are_not_browser_cacheable():
    with TestClient(app) as client:
        response = client.get("/api/market/quotes")

    assert response.headers["cache-control"] == "no-store"


def test_untrusted_host_is_rejected():
    with TestClient(app) as client:
        response = client.get("/health", headers={"Host": "evil.example"})

    assert response.status_code == 400


def test_protected_read_endpoints_require_authentication():
    paths = [
        "/api/market/quote/BTC%2FUSD",
        "/api/market/quotes",
        "/api/market/status",
        "/api/market/scanner",
        "/api/analysis/BTC%2FUSD",
        "/api/watchlists",
    ]

    with TestClient(app) as client:
        responses = [client.get(path) for path in paths]

    assert [response.status_code for response in responses] == [401] * len(paths)


def test_cors_allows_configured_local_development_origin():
    with TestClient(app) as client:
        response = client.options(
            "/api/analysis/BTC%2FUSD",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_analysis_maps_runtime_feature_failure_to_503(authenticated_client, monkeypatch):
    dataset = make_dataset()

    async def fake_get_candles(symbol, timeframe, limit):
        return dataset

    def failing_feature_engine(dataset):
        raise RuntimeError("feature engine unavailable")

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    monkeypatch.setattr("app.api.analysis.calculate_feature_set", failing_feature_engine)

    response = authenticated_client.get("/api/analysis/BTC%2FUSD")

    assert response.status_code == 503
    assert response.json()["detail"] == "feature engine unavailable"


def test_feature_engine_rejects_zero_minimum_history():
    with pytest.raises(ValueError, match="greater than zero"):
        FeatureEngine(minimum_candles=0)


def test_feature_engine_rejects_negative_minimum_history():
    with pytest.raises(ValueError, match="greater than zero"):
        FeatureEngine(minimum_candles=-1)


def test_feature_engine_preserves_source_and_timeframe():
    result = FeatureEngine().calculate(make_dataset())

    assert result.source == "test_provider"
    assert result.symbol == "BTC/USD"
    assert result.timeframe == Timeframe.HOUR_1
    assert result.candle_count == 40
    assert result.latest_candle_timestamp == datetime(
        2026, 1, 2, 15, tzinfo=timezone.utc
    )


def test_production_csrf_rejects_untrusted_origin(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "cors_origins", "https://research-dusky-six.vercel.app")
    token = _csrf_token("access-token")

    with pytest.raises(HTTPException, match="origin validation"):
        _require_csrf(
            csrf_cookie=token,
            csrf_header=token,
            access_token="access-token",
            origin="https://evil.example",
        )


def test_production_csrf_accepts_configured_origin(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "cors_origins", "https://research-dusky-six.vercel.app")
    token = _csrf_token("access-token")

    _require_csrf(
        csrf_cookie=token,
        csrf_header=token,
        access_token="access-token",
        origin="https://research-dusky-six.vercel.app",
    )


def test_production_settings_reject_default_csrf_secret():
    with pytest.raises(ValidationError, match="CSRF_SECRET"):
        Settings(
            app_env="production",
            csrf_secret="development-only-change-me",
            cors_origins="https://research-dusky-six.vercel.app",
            twelve_data_api_key="test-provider-key",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
            auth_password_reset_redirect_url="https://research-dusky-six.vercel.app/?reset=1",
        )


def test_production_settings_require_provider_and_supabase_configuration():
    with pytest.raises(ValidationError, match="TWELVE_DATA_API_KEY"):
        Settings(
            app_env="production",
            csrf_secret="x" * 32,
            cors_origins="https://research-dusky-six.vercel.app",
            twelve_data_api_key="",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
            auth_password_reset_redirect_url="https://research-dusky-six.vercel.app/?reset=1",
        )


def test_production_settings_reject_local_only_trusted_hosts():
    with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
        Settings(
            app_env="production",
            csrf_secret="x" * 32,
            cors_origins="https://research-dusky-six.vercel.app",
            trusted_hosts="localhost,127.0.0.1,testserver",
            twelve_data_api_key="test-provider-key",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
            auth_password_reset_redirect_url="https://research-dusky-six.vercel.app/?reset=1",
        )


def test_production_settings_accept_valid_security_configuration():
    configured = Settings(
        app_env="production",
        csrf_secret="x" * 32,
        cors_origins="https://research-dusky-six.vercel.app",
        trusted_hosts="research-76vr.onrender.com",
        twelve_data_api_key="test-provider-key",
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="test-publishable-key",
        auth_password_reset_redirect_url="https://research-dusky-six.vercel.app/?reset=1",
    )

    assert configured.app_env == "production"
    assert configured.cors_origins == "https://research-dusky-six.vercel.app"
    assert configured.trusted_hosts == "research-76vr.onrender.com"
