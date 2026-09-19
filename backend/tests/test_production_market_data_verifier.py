from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from scripts.verify_production_market_data import (
    MAX_REQUEST_ATTEMPTS,
    RETRY_BACKOFF_BASE_SECONDS,
    VerificationTransportError,
    request,
)


def test_read_timeout_retries_with_exponential_backoff() -> None:
    client = Mock()
    response = Mock(spec=httpx.Response)
    client.get.side_effect = [
        httpx.ReadTimeout("first timeout"),
        httpx.ReadTimeout("second timeout"),
        response,
    ]

    with patch("scripts.verify_production_market_data.time.sleep") as sleep:
        result = request(client, "https://example.test", stage="CoinGecko independent price")

    assert result is response
    assert client.get.call_count == 3
    assert sleep.call_args_list[0].args == (RETRY_BACKOFF_BASE_SECONDS,)
    assert sleep.call_args_list[1].args == (RETRY_BACKOFF_BASE_SECONDS * 2,)


def test_connect_timeout_retries_then_reports_stage() -> None:
    client = Mock()
    client.get.side_effect = httpx.ConnectTimeout("connection timeout")

    with patch("scripts.verify_production_market_data.time.sleep") as sleep:
        with pytest.raises(VerificationTransportError) as exc_info:
            request(client, "https://example.test", stage="Render health")

    error = exc_info.value
    assert error.stage == "Render health"
    assert error.attempts == MAX_REQUEST_ATTEMPTS
    assert "ConnectTimeout" in str(error)
    assert client.get.call_count == MAX_REQUEST_ATTEMPTS
    assert sleep.call_count == MAX_REQUEST_ATTEMPTS - 1


def test_non_timeout_http_error_is_not_retried() -> None:
    client = Mock()
    client.get.side_effect = httpx.ReadError("non-timeout transport failure")

    with patch("scripts.verify_production_market_data.time.sleep") as sleep:
        with pytest.raises(httpx.ReadError):
            request(client, "https://example.test", stage="Production market quote")

    assert client.get.call_count == 1
    sleep.assert_not_called()


def test_retry_helper_is_bounded_and_caps_backoff() -> None:
    client = Mock()
    client.get.side_effect = httpx.ReadTimeout("timeout")

    with patch("scripts.verify_production_market_data.time.sleep") as sleep:
        with pytest.raises(VerificationTransportError) as exc_info:
            request(client, "https://example.test", stage="Protected provider fallback")

    assert exc_info.value.attempts == MAX_REQUEST_ATTEMPTS
    assert all(call.args[0] <= 4.0 for call in sleep.call_args_list)


def test_fallback_symbol_defaults_to_secondary_provider_supported_24_7_pair(monkeypatch) -> None:
    from scripts.verify_production_market_data import DEFAULT_FALLBACK_SYMBOL

    monkeypatch.delenv("MARKET_FALLBACK_SYMBOL", raising=False)
    assert DEFAULT_FALLBACK_SYMBOL == "BTC/USDT"
    from scripts.verify_production_market_data import DEFAULT_FALLBACK_TIMEFRAME
    assert DEFAULT_FALLBACK_TIMEFRAME == "1d"
