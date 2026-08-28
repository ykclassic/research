from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import auth


@pytest.fixture
def production_oidc_settings(monkeypatch):
    monkeypatch.setattr(auth.settings, "github_oidc_repository", "ykclassic/research")
    monkeypatch.setattr(
        auth.settings,
        "github_oidc_workflow",
        ".github/workflows/production-market-data-verification.yml",
    )
    monkeypatch.setattr(auth.settings, "github_oidc_ref", "refs/heads/main")
    monkeypatch.setattr(auth.settings, "github_oidc_audience", "research-production-verifier")


def valid_claims() -> dict[str, str]:
    return {
        "repository": "ykclassic/research",
        "ref": "refs/heads/main",
        "workflow_ref": (
            "ykclassic/research/"
            ".github/workflows/production-market-data-verification.yml@refs/heads/main"
        ),
        "event_name": "workflow_dispatch",
    }


def test_github_oidc_claims_accept_trusted_workflow(production_oidc_settings):
    auth._validate_github_oidc_claims(valid_claims())


@pytest.mark.parametrize(
    "claim,value",
    [
        ("repository", "attacker/other-repo"),
        ("ref", "refs/heads/feature"),
        ("workflow_ref", "ykclassic/research/.github/workflows/other.yml@refs/heads/main"),
        ("event_name", "pull_request"),
    ],
)
def test_github_oidc_claims_reject_untrusted_context(
    production_oidc_settings,
    claim: str,
    value: str,
):
    claims = valid_claims()
    claims[claim] = value

    with pytest.raises(HTTPException) as exc_info:
        auth._validate_github_oidc_claims(claims)

    assert exc_info.value.status_code == 403


def test_verifier_dependency_uses_bearer_oidc_without_supabase_cookie(
    production_oidc_settings,
    monkeypatch,
):
    called: dict[str, str] = {}

    def fake_verify(token: str) -> None:
        called["token"] = token

    monkeypatch.setattr(auth, "_verify_github_oidc_token", fake_verify)

    result = auth.get_current_user_or_github_actions(
        authorization="Bearer short-lived-github-oidc-token",
        access_token=None,
    )

    assert result is None
    assert called["token"] == "short-lived-github-oidc-token"


def test_verifier_dependency_rejects_non_bearer_authorization(
    production_oidc_settings,
):
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user_or_github_actions(
            authorization="Basic credentials",
            access_token=None,
        )

    assert exc_info.value.status_code == 401
