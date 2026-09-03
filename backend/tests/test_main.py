from __future__ import annotations

import asyncio

from app.main import health


def test_health_exposes_render_deployment_provenance(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    monkeypatch.setenv("RENDER_GIT_REPO_SLUG", "ykclassic/research")

    payload = asyncio.run(health())

    assert payload["deployment_commit"] == "abc123"
    assert payload["deployment_branch"] == "main"
    assert payload["deployment_repository"] == "ykclassic/research"
