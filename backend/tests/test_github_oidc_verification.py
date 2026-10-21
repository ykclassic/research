from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.api import auth as auth_api
from app.config import settings


@pytest.fixture
def oidc_keys(monkeypatch: pytest.MonkeyPatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token: str):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(auth_api, "_github_oidc_jwks_client", lambda: FakeJwksClient())
    return private_key


def _claims(**overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": settings.github_oidc_issuer,
        "aud": settings.github_oidc_audience,
        "sub": "repo:ykclassic/research:ref:refs/heads/main",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "repository": settings.github_oidc_repository,
        "ref": settings.github_oidc_ref,
        "workflow_ref": (
            f"{settings.github_oidc_repository}/"
            f"{settings.github_oidc_workflow}@{settings.github_oidc_ref}"
        ),
        "event_name": "push",
    }
    claims.update(overrides)
    return claims


def _token(private_key, claims=None):
    return jwt.encode(claims or _claims(), private_key, algorithm="RS256")


def test_oidc_verifier_accepts_valid_signed_and_scoped_token(oidc_keys):
    auth_api._verify_github_oidc_token(_token(oidc_keys))


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-jwt",
        "eyJhbGciOiJub25lIn0.eyJzdWIiOiJub25lIn0.",
    ],
)
def test_oidc_verifier_rejects_missing_or_malformed_token(oidc_keys, token):
    with pytest.raises(HTTPException) as exc:
        auth_api._verify_github_oidc_token(token)
    assert exc.value.status_code == 401


def test_oidc_verifier_rejects_expired_token(oidc_keys):
    expired = _claims(
        exp=int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),
        iat=int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()),
    )
    with pytest.raises(HTTPException) as exc:
        auth_api._verify_github_oidc_token(_token(oidc_keys, expired))
    assert exc.value.status_code == 401


def test_oidc_verifier_rejects_invalid_signature(oidc_keys):
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(HTTPException) as exc:
        auth_api._verify_github_oidc_token(_token(other_private_key))
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "https://untrusted-issuer.invalid"},
        {"aud": "untrusted-audience"},
        {"sub": None},
        {"exp": None},
        {"iat": None},
    ],
)
def test_oidc_verifier_rejects_invalid_issuer_audience_or_required_claims(oidc_keys, override):
    claims = _claims(**override)
    with pytest.raises(HTTPException) as exc:
        auth_api._verify_github_oidc_token(_token(oidc_keys, claims))
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    ("claim", "value", "detail"),
    [
        ("repository", "attacker/repo", "repository is not trusted"),
        ("ref", "refs/heads/feature/untrusted", "ref is not trusted"),
        ("workflow_ref", "ykclassic/research/.github/workflows/untrusted.yml@refs/heads/main", "workflow is not trusted"),
        ("event_name", "pull_request_target", "event is not trusted"),
    ],
)
def test_oidc_verifier_rejects_incorrectly_scoped_token(oidc_keys, claim, value, detail):
    claims = _claims(**{claim: value})
    with pytest.raises(HTTPException, match=detail) as exc:
        auth_api._verify_github_oidc_token(_token(oidc_keys, claims))
    assert exc.value.status_code == 403
