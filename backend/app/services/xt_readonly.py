from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


XT_SPOT_ORIGIN = "https://sapi.xt.com"
XT_BALANCES_PATH = "/spot/v4/balances"
XT_RECEIVE_WINDOW_MS = 5000


class XtProviderError(RuntimeError):
    """Sanitized XT read-only provider failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class XtBalance:
    currency: str
    available: Decimal
    frozen: Decimal
    total: Decimal


@dataclass(frozen=True)
class XtPortfolioSnapshot:
    provider: str
    account_fingerprint: str
    observed_at: datetime
    balances: tuple[XtBalance, ...]


def _decimal_amount(value: Any, field: str) -> Decimal:
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        raise XtProviderError("invalid_response")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise XtProviderError("invalid_response") from None
    if not amount.is_finite() or amount < 0:
        raise XtProviderError("invalid_response")
    return amount


def _parse_balances(payload: Any) -> tuple[XtBalance, ...]:
    if not isinstance(payload, dict) or payload.get("rc") != 0:
        raise XtProviderError("provider_rejected_request")
    result = payload.get("result")
    assets = result.get("assets") if isinstance(result, dict) else None
    if not isinstance(assets, list):
        raise XtProviderError("invalid_response")

    parsed: list[XtBalance] = []
    seen: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise XtProviderError("invalid_response")
        currency = asset.get("currency")
        if not isinstance(currency, str) or not currency.strip():
            raise XtProviderError("invalid_response")
        currency = currency.strip().upper()
        if currency in seen:
            raise XtProviderError("invalid_response")
        seen.add(currency)

        available = _decimal_amount(asset.get("availableAmount"), "availableAmount")
        frozen = _decimal_amount(asset.get("frozenAmount"), "frozenAmount")
        total = _decimal_amount(asset.get("totalAmount"), "totalAmount")
        if total < available or total < frozen:
            raise XtProviderError("invalid_response")
        parsed.append(XtBalance(currency=currency, available=available, frozen=frozen, total=total))
    return tuple(parsed)


class XtReadOnlyClient:
    """Minimal XT Spot client. It exposes a single fixed GET endpoint only."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        timeout_seconds: float = 5.0,
        receive_window_ms: int = XT_RECEIVE_WINDOW_MS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise XtProviderError("credentials_missing")
        if not isinstance(api_secret, str) or not api_secret.strip():
            raise XtProviderError("credentials_missing")
        if timeout_seconds <= 0 or not 1000 <= receive_window_ms <= XT_RECEIVE_WINDOW_MS:
            raise ValueError("Invalid XT client timeout or receive window.")
        self._api_key = api_key.strip()
        self._api_secret = api_secret.strip()
        self._timeout_seconds = timeout_seconds
        self._receive_window_ms = receive_window_ms
        self._transport = transport

    def _signing_preimage(self, timestamp_ms: int) -> str:
        fields = {
            "validate-algorithms": "HmacSHA256",
            "validate-appkey": self._api_key,
            "validate-recvwindow": str(self._receive_window_ms),
            "validate-timestamp": str(timestamp_ms),
        }
        canonical = "&".join(f"{key}={fields[key]}" for key in sorted(fields))
        return f"{canonical}#GET#{XT_BALANCES_PATH}"

    def _headers(self, timestamp_ms: int) -> dict[str, str]:
        preimage = self._signing_preimage(timestamp_ms)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            preimage.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "validate-algorithms": "HmacSHA256",
            "validate-appkey": self._api_key,
            "validate-recvwindow": str(self._receive_window_ms),
            "validate-timestamp": str(timestamp_ms),
            "validate-signature": signature,
        }

    async def get_balances(self) -> XtPortfolioSnapshot:
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        headers = self._headers(timestamp_ms)
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.get(f"{XT_SPOT_ORIGIN}{XT_BALANCES_PATH}", headers=headers)
        except httpx.TimeoutException:
            raise XtProviderError("provider_timeout") from None
        except httpx.HTTPError:
            raise XtProviderError("provider_unavailable") from None

        if 300 <= response.status_code < 400:
            raise XtProviderError("unexpected_redirect")
        if response.status_code in (401,):
            raise XtProviderError("authentication_failed")
        if response.status_code in (403,):
            raise XtProviderError("permission_denied")
        if response.status_code == 429:
            raise XtProviderError("rate_limited")
        if response.status_code >= 500:
            raise XtProviderError("provider_unavailable")
        if response.status_code != 200:
            raise XtProviderError("provider_rejected_request")
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            raise XtProviderError("invalid_response") from None

        balances = _parse_balances(payload)
        return XtPortfolioSnapshot(
            provider="xt_spot",
            account_fingerprint=hashlib.sha256(self._api_key.encode("utf-8")).hexdigest()[:16],
            observed_at=datetime.now(timezone.utc),
            balances=balances,
        )
