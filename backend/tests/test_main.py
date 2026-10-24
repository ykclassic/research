from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app, health


def test_health_exposes_render_deployment_provenance(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    monkeypatch.setenv("RENDER_GIT_REPO_SLUG", "ykclassic/research")

    payload = asyncio.run(health())

    assert payload["deployment_commit"] == "abc123"
    assert payload["deployment_branch"] == "main"
    assert payload["deployment_repository"] == "ykclassic/research"


def test_openapi_schema_builds_for_all_registered_routes() -> None:
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    request_schema = schema["paths"]["/api/infrastructure/export-schedules"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/ExportScheduleCreate")
