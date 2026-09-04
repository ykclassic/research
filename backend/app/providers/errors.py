from __future__ import annotations

from enum import Enum

import httpx


class ProviderErrorCode(str, Enum):
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    SYMBOL_UNSUPPORTED = "SYMBOL_UNSUPPORTED"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    ALL_PROVIDERS_UNAVAILABLE = "ALL_PROVIDERS_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


_ERROR_LABELS = {
    ProviderErrorCode.RATE_LIMITED: "Rate limited",
    ProviderErrorCode.QUOTA_EXHAUSTED: "Quota exhausted",
    ProviderErrorCode.AUTHENTICATION_FAILURE: "Authentication failure",
    ProviderErrorCode.SYMBOL_UNSUPPORTED: "Symbol unsupported",
    ProviderErrorCode.PROVIDER_TIMEOUT: "Provider timeout",
    ProviderErrorCode.PROVIDER_UNAVAILABLE: "Provider unavailable",
    ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE: "All providers unavailable",
    ProviderErrorCode.UNKNOWN: "Provider error",
}


def error_label(code: ProviderErrorCode | str | None) -> str:
    try:
        normalized = ProviderErrorCode(code) if code is not None else ProviderErrorCode.UNKNOWN
    except ValueError:
        normalized = ProviderErrorCode.UNKNOWN
    return _ERROR_LABELS[normalized]


def classify_provider_error(
    exc: BaseException | None = None,
    *,
    message: str | None = None,
    status_code: int | None = None,
) -> ProviderErrorCode:
    text = (message or str(exc or "")).lower()
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, TimeoutError)):
        return ProviderErrorCode.PROVIDER_TIMEOUT

    response = getattr(exc, "response", None)
    status = status_code or getattr(response, "status_code", None)
    if status in {401, 403}:
        return ProviderErrorCode.AUTHENTICATION_FAILURE
    if status == 429:
        if any(term in text for term in ("credit", "credits", "quota", "daily limit", "limit reached")):
            return ProviderErrorCode.QUOTA_EXHAUSTED
        return ProviderErrorCode.RATE_LIMITED
    if status in {408, 504}:
        return ProviderErrorCode.PROVIDER_TIMEOUT
    if status is not None and 500 <= status <= 599:
        return ProviderErrorCode.PROVIDER_UNAVAILABLE
    if status in {400, 404, 414} and any(
        term in text for term in ("symbol", "instrument", "ticker", "not found", "unsupported")
    ):
        return ProviderErrorCode.SYMBOL_UNSUPPORTED
    if any(term in text for term in ("invalid symbol", "symbol not found", "unsupported symbol", "instrument not found")):
        return ProviderErrorCode.SYMBOL_UNSUPPORTED
    if any(term in text for term in ("rate limit", "too many requests", "throttl")):
        return ProviderErrorCode.RATE_LIMITED
    if any(term in text for term in ("quota", "credit", "credits left", "daily limit")):
        return ProviderErrorCode.QUOTA_EXHAUSTED
    if any(term in text for term in ("provider unavailable", "upstream unavailable", "service unavailable", "temporarily unavailable")):
        return ProviderErrorCode.PROVIDER_UNAVAILABLE
    if isinstance(exc, httpx.TimeoutException):
        return ProviderErrorCode.PROVIDER_TIMEOUT
    if isinstance(exc, httpx.HTTPError):
        return ProviderErrorCode.PROVIDER_UNAVAILABLE
    return ProviderErrorCode.UNKNOWN


def retryable_provider_error(code: ProviderErrorCode) -> bool:
    return code in {
        ProviderErrorCode.PROVIDER_TIMEOUT,
        ProviderErrorCode.PROVIDER_UNAVAILABLE,
    }
