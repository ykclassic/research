from __future__ import annotations

import httpx
import pytest

from scripts import verify_production_mtf as verifier


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, *, params, headers):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://example.test/api/mtf/BTC/USD"),
    )


def test_mtf_request_retries_read_timeout_then_returns_response(monkeypatch) -> None:
    monkeypatch.setattr(verifier.time, "sleep", lambda _seconds: None)
    client = FakeClient([httpx.ReadTimeout("slow response"), response(200)])

    result = verifier.request_mtf(
        client,
        "https://example.test/api/mtf/BTC/USD",
        params={"limit": 250},
        headers={"Authorization": "Bearer test-token"},
    )

    assert result.status_code == 200
    assert client.calls == 2


def test_mtf_request_retries_transient_503(monkeypatch) -> None:
    monkeypatch.setattr(verifier.time, "sleep", lambda _seconds: None)
    client = FakeClient([response(503), response(200)])

    result = verifier.request_mtf(
        client,
        "https://example.test/api/mtf/BTC/USD",
        params={"limit": 250},
        headers={},
    )

    assert result.status_code == 200
    assert client.calls == 2


def test_mtf_request_does_not_retry_client_errors(monkeypatch) -> None:
    monkeypatch.setattr(verifier.time, "sleep", lambda _seconds: None)
    client = FakeClient([response(401)])

    result = verifier.request_mtf(
        client,
        "https://example.test/api/mtf/BTC/USD",
        params={"limit": 250},
        headers={},
    )

    assert result.status_code == 401
    assert client.calls == 1


def test_mtf_request_fails_after_bounded_timeout_retries(monkeypatch) -> None:
    monkeypatch.setattr(verifier.time, "sleep", lambda _seconds: None)
    client = FakeClient([
        httpx.ReadTimeout("slow response"),
        httpx.ReadTimeout("still slow"),
    ])

    with pytest.raises(httpx.ReadTimeout):
        verifier.request_mtf(
            client,
            "https://example.test/api/mtf/BTC/USD",
            params={"limit": 250},
            headers={},
        )

    assert client.calls == verifier.MAX_REQUEST_ATTEMPTS == 2
