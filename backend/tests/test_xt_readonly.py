from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

import httpx
import pytest

from app.services.xt_readonly import (
    XT_BALANCES_PATH,
    XT_SPOT_ORIGIN,
    XtProviderError,
    XtReadOnlyClient,
    _parse_balances,
)


API_KEY = "test-app-key"
API_SECRET = "test-secret"


def _response(status_code: int, payload: object) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.mark.asyncio
async def test_read_only_client_signs_fixed_get_and_parses_balances() -> None:
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return _response(
            200,
            {
                "rc": 0,
                "result": {
                    "assets": [
                        {
                            "currency": "usdt",
                            "availableAmount": "12.3400",
                            "frozenAmount": "1.6600",
                            "totalAmount": "14.0000",
                        }
                    ]
                },
            },
        )

    client = XtReadOnlyClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        transport=httpx.MockTransport(handler),
    )
    snapshot = await client.get_balances()

    assert len(observed) == 1
    request = observed[0]
    assert request.method == "GET"
    assert str(request.url) == f"{XT_SPOT_ORIGIN}{XT_BALANCES_PATH}"
    assert request.headers["validate-appkey"] == API_KEY
    assert request.headers["validate-algorithms"] == "HmacSHA256"
    assert request.headers["validate-recvwindow"] == "5000"
    timestamp = request.headers["validate-timestamp"]
    fields = {
        "validate-algorithms": "HmacSHA256",
        "validate-appkey": API_KEY,
        "validate-recvwindow": "5000",
        "validate-timestamp": timestamp,
    }
    preimage = "&".join(f"{key}={fields[key]}" for key in sorted(fields)) + f"#GET#{XT_BALANCES_PATH}"
    expected = hmac.new(API_SECRET.encode(), preimage.encode(), hashlib.sha256).hexdigest()
    assert request.headers["validate-signature"] == expected
    assert snapshot.provider == "xt_spot"
    assert snapshot.account_fingerprint == hashlib.sha256(API_KEY.encode()).hexdigest()[:16]
    assert snapshot.balances[0].currency == "USDT"
    assert snapshot.balances[0].available == Decimal("12.3400")
    assert snapshot.balances[0].frozen == Decimal("1.6600")
    assert snapshot.balances[0].total == Decimal("14.0000")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (301, "unexpected_redirect"),
        (401, "authentication_failed"),
        (403, "permission_denied"),
        (429, "rate_limited"),
        (503, "provider_unavailable"),
        (400, "provider_rejected_request"),
    ],
)
async def test_provider_http_errors_are_sanitized(status: int, reason: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="secret provider body must not escape")

    client = XtReadOnlyClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(XtProviderError) as caught:
        await client.get_balances()
    assert caught.value.reason_code == reason
    assert "secret provider body" not in str(caught.value)


@pytest.mark.asyncio
async def test_timeout_fails_closed_without_leaking_exception() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("credential-bearing provider diagnostic")

    client = XtReadOnlyClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(XtProviderError) as caught:
        await client.get_balances()
    assert caught.value.reason_code == "provider_timeout"
    assert "credential-bearing" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"rc": 1, "result": {"assets": []}},
        {"rc": 0, "result": {}},
        {"rc": 0, "result": {"assets": "not-a-list"}},
        {"rc": 0, "result": {"assets": [{"currency": "BTC"}]}},
        {"rc": 0, "result": {"assets": [{"currency": "BTC", "availableAmount": "NaN", "frozenAmount": "0", "totalAmount": "NaN"}]}},
        {"rc": 0, "result": {"assets": [{"currency": "BTC", "availableAmount": "-1", "frozenAmount": "0", "totalAmount": "1"}]}},
        {"rc": 0, "result": {"assets": [{"currency": "BTC", "availableAmount": "2", "frozenAmount": "0", "totalAmount": "1"}]}},
        {"rc": 0, "result": {"assets": [{"currency": "BTC", "availableAmount": "0", "frozenAmount": "0", "totalAmount": "1"}, {"currency": "btc", "availableAmount": "0", "frozenAmount": "0", "totalAmount": "1"}]}},
    ],
)
async def test_invalid_provider_payload_fails_closed(payload: object) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = XtReadOnlyClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(XtProviderError):
        await client.get_balances()


@pytest.mark.asyncio
async def test_missing_credentials_are_rejected() -> None:
    with pytest.raises(XtProviderError) as caught:
        XtReadOnlyClient(api_key="", api_secret=API_SECRET)
    assert caught.value.reason_code == "credentials_missing"


def test_balance_parser_preserves_empty_account_and_decimal_precision() -> None:
    assert _parse_balances({"rc": 0, "result": {"assets": []}}) == ()
