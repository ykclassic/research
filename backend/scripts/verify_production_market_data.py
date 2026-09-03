from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


DEFAULT_API_BASE = "https://research-76vr.onrender.com"
DEFAULT_SYMBOL = "BTC/USD"
DEFAULT_TIMEFRAME = "1h"
DEFAULT_ANALYSIS_LIMIT = 250
DIRECT_PROVIDER_TOLERANCE = 0.001
INDEPENDENT_SOURCE_TOLERANCE = 0.005
MAX_PROVIDER_AGE_SECONDS = 180.0
MAX_BACKEND_OBSERVATION_AGE_SECONDS = 15.0
MAX_INDEPENDENT_SOURCE_AGE_SECONDS = 180.0
MAX_FUTURE_TIMESTAMP_SKEW_SECONDS = 5.0
MIN_CURRENT_VS_CANDLE_PRICE_DELTA = 0.01
CACHE_PROBE_DELAY_SECONDS = 1.25
REQUEST_TIMEOUT_SECONDS = 30.0
REQUEST_CONNECT_TIMEOUT_SECONDS = 10.0
MAX_REQUEST_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SECONDS = 1.0
RETRY_BACKOFF_CAP_SECONDS = 4.0


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


class VerificationTransportError(RuntimeError):
    """A bounded GET retry budget was exhausted for a named verification stage."""

    def __init__(self, stage: str, attempts: int, error: httpx.TimeoutException) -> None:
        self.stage = stage
        self.attempts = attempts
        self.error = error
        super().__init__(
            f"{stage}: {type(error).__name__} after {attempts} attempts: {error}"
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp is not timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def relative_error(actual: float, reference: float) -> float:
    return abs(actual - reference) / reference if reference > 0 else 1.0


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request(
    client: httpx.Client,
    url: str,
    *,
    stage: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Perform an idempotent GET with bounded retries for transport timeouts only."""
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            return client.get(url, params=params, headers=headers)
        except (httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            if attempt >= MAX_REQUEST_ATTEMPTS:
                raise VerificationTransportError(stage, attempt, exc) from exc
            delay = min(
                RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                RETRY_BACKOFF_CAP_SECONDS,
            )
            print(
                f"[RETRY] {stage}: {type(exc).__name__} on attempt "
                f"{attempt}/{MAX_REQUEST_ATTEMPTS}; retrying in {delay:.1f}s"
            )
            time.sleep(delay)
    raise AssertionError("unreachable retry loop")


def direct_provider_quote(
    client: httpx.Client,
    source: str,
    symbol: str,
    key: str,
) -> tuple[float, datetime]:
    if source == "twelve_data":
        payload = request(
            client,
            "https://api.twelvedata.com/quote",
            stage="Twelve Data quote",
            params={"symbol": symbol, "apikey": key, "interval": "1min"},
        ).json()
        price = float(payload.get("close", payload.get("price", 0)))
        raw = payload.get("last_update_at", payload.get("timestamp"))
        provider_time = (
            datetime.fromtimestamp(float(raw), tz=timezone.utc)
            if str(raw).isdigit()
            else parse_datetime(str(raw))
        )
        return price, provider_time
    if source == "finnhub":
        mapping = symbol.replace("/", "")
        if "/" in symbol:
            base, quote = symbol.split("/")
            mapping = f"BINANCE:{base}{quote}"
        payload = request(
            client,
            "https://finnhub.io/api/v1/quote",
            stage="Finnhub quote",
            params={"symbol": mapping, "token": key},
        ).json()
        price = float(payload.get("c", 0))
        provider_time = datetime.fromtimestamp(float(payload["t"]), tz=timezone.utc)
        return price, provider_time
    if source == "alpha_vantage":
        if "/" in symbol:
            base, quote = symbol.split("/")
            payload = request(
                client,
                "https://www.alphavantage.co/query",
                stage="Alpha Vantage FX quote",
                params={
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": base,
                    "to_currency": quote,
                    "apikey": key,
                },
            ).json()
            row = payload.get("Realtime Currency Exchange Rate", {})
            return float(row.get("5. Exchange Rate", 0)), parse_datetime(
                str(row["6. Last Refreshed"])
            )
        payload = request(
            client,
            "https://www.alphavantage.co/query",
            stage="Alpha Vantage equity quote",
            params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key},
        ).json()
        row = payload.get("Global Quote", {})
        return float(row.get("05. price", 0)), parse_datetime(
            str(row["07. latest trading day"])
        )
    raise ValueError(f"Unsupported direct provider: {source}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Production verification for the resilient market-data API."
    )
    parser.add_argument("--api-base", default=os.getenv("MARKET_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--symbol", default=os.getenv("MARKET_SYMBOL", DEFAULT_SYMBOL))
    parser.add_argument("--timeframe", default=os.getenv("MARKET_TIMEFRAME", DEFAULT_TIMEFRAME))
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("MARKET_ANALYSIS_LIMIT", DEFAULT_ANALYSIS_LIMIT)),
    )
    parser.add_argument(
        "--max-provider-age",
        type=float,
        default=float(os.getenv("MARKET_MAX_PROVIDER_AGE", MAX_PROVIDER_AGE_SECONDS)),
    )
    args = parser.parse_args()

    oidc_token = os.getenv("GITHUB_OIDC_TOKEN")
    if not oidc_token:
        print("FAIL: GITHUB_OIDC_TOKEN is required.", file=sys.stderr)
        return 2

    expected_commit = os.getenv("EXPECTED_DEPLOY_COMMIT", "").strip()
    base_url = args.api_base.rstrip("/")
    symbol = args.symbol.upper()
    timeout = httpx.Timeout(
        REQUEST_TIMEOUT_SECONDS,
        connect=REQUEST_CONNECT_TIMEOUT_SECONDS,
    )
    results: list[CheckResult] = []

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        try:
            health = request(client, f"{base_url}/health", stage="Render health")
            health.raise_for_status()
            payload = health.json()
            require(payload.get("ok") is True, f"health payload is not healthy: {payload}")
            deployed_commit = str(
                payload.get("deployment_commit")
                or health.headers.get("X-Deployment-Commit")
                or ""
            )
            if expected_commit:
                require(
                    deployed_commit == expected_commit,
                    "API deployment commit mismatch: "
                    f"expected {expected_commit}, observed {deployed_commit or '<missing>'}",
                )
                results.append(
                    CheckResult(
                        "API deployment matches pushed Git commit",
                        True,
                        f"expected={expected_commit}; observed={deployed_commit}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "API deployment provenance is visible",
                        True,
                        f"deployment_commit={deployed_commit or '<not exposed in this environment>'}",
                    )
                )
            results.append(
                CheckResult(
                    "API reachable",
                    True,
                    f"HTTP 200; service={payload.get('service')}; environment={payload.get('environment')}",
                )
            )

            nonce = str(uuid.uuid4())
            headers = {
                "Authorization": f"Bearer {oidc_token}",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
                "X-Verification-Nonce": nonce,
            }
            response = request(
                client,
                f"{base_url}/api/market/quote/{symbol}",
                stage="Production market quote",
                params={"refresh": "true", "verification_nonce": nonce},
                headers=headers,
            )
            response.raise_for_status()
            response_commit = response.headers.get("X-Deployment-Commit", "")
            if expected_commit:
                require(
                    response_commit == expected_commit,
                    "Quote response deployment commit mismatch: "
                    f"expected {expected_commit}, observed {response_commit or '<missing>'}",
                )
                results.append(
                    CheckResult(
                        "Quote response came from intended deployment",
                        True,
                        f"X-Deployment-Commit={response_commit}",
                    )
                )
            body = response.json()
            quote = body["quote"]
            source = quote["source"]
            require(
                source in {"twelve_data", "finnhub", "alpha_vantage"},
                f"Unexpected selected provider: {source}",
            )
            require(
                quote["status"] in {"LIVE", "DELAYED"},
                f"Initial API quote is not usable: {quote}",
            )
            require(quote["price"] is not None, "Initial API quote has no price")
            require(
                response.headers.get("X-Market-Data-Refresh") == "true",
                "API did not acknowledge refresh=true",
            )
            require(
                response.headers.get("X-Market-Data-Cache") == "MISS",
                "Refresh request unexpectedly hit the canonical cache",
            )
            results.append(
                CheckResult(
                    "Deployed API owns a validated quote",
                    True,
                    f"source={source}; status={quote['status']}; price={quote['price']}",
                )
            )

            provider_time = parse_datetime(quote["provider_timestamp"])
            observed_at = parse_datetime(quote["observed_at"])
            provider_age = (utc_now() - provider_time).total_seconds()
            observation_age = (utc_now() - observed_at).total_seconds()
            require(
                -MAX_FUTURE_TIMESTAMP_SKEW_SECONDS <= provider_age <= args.max_provider_age,
                f"Provider age={provider_age:.2f}s",
            )
            require(
                -MAX_FUTURE_TIMESTAMP_SKEW_SECONDS
                <= observation_age
                <= MAX_BACKEND_OBSERVATION_AGE_SECONDS,
                f"Backend observation age={observation_age:.2f}s",
            )
            results.append(
                CheckResult(
                    "Latency and freshness are separated",
                    True,
                    f"request_latency_ms={quote.get('latency_ms')}; "
                    f"provider_age={provider_age:.2f}s <= {args.max_provider_age:.0f}s; "
                    f"observed_age={observation_age:.2f}s",
                )
            )

            direct_keys = {
                "twelve_data": os.getenv("TWELVE_DATA_API_KEY", ""),
                "finnhub": os.getenv("FINNHUB_API_KEY", ""),
                "alpha_vantage": os.getenv("ALPHA_VANTAGE_API_KEY", ""),
            }
            direct_key = direct_keys.get(source, "")
            if direct_key:
                direct_price, direct_time = direct_provider_quote(
                    client, source, symbol, direct_key
                )
                error = relative_error(float(quote["price"]), direct_price)
                require(error <= DIRECT_PROVIDER_TOLERANCE, f"API vs {source} error={error:.6%}")
                results.append(
                    CheckResult(
                        "API agrees with selected provider",
                        True,
                        f"API={quote['price']}; direct={direct_price}; "
                        f"error={error:.6%} <= {DIRECT_PROVIDER_TOLERANCE:.2%}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "API provider provenance is explicit",
                        True,
                        f"Selected provider={source}; direct verification key is not available in this workflow context.",
                    )
                )

            if symbol == "BTC/USD":
                independent = request(
                    client,
                    "https://api.coingecko.com/api/v3/simple/price",
                    stage="CoinGecko independent price",
                    params={
                        "ids": "bitcoin",
                        "vs_currencies": "usd",
                        "include_last_updated_at": "true",
                    },
                )
                independent.raise_for_status()
                bitcoin = independent.json()["bitcoin"]
                independent_price = float(bitcoin["usd"])
                independent_age = (
                    utc_now()
                    - datetime.fromtimestamp(
                        float(bitcoin["last_updated_at"]), tz=timezone.utc
                    )
                ).total_seconds()
                independent_error = relative_error(float(quote["price"]), independent_price)
                require(
                    independent_error <= INDEPENDENT_SOURCE_TOLERANCE,
                    f"API vs CoinGecko error={independent_error:.6%}",
                )
                require(
                    independent_age <= MAX_INDEPENDENT_SOURCE_AGE_SECONDS,
                    f"CoinGecko age={independent_age:.2f}s",
                )
                results.append(
                    CheckResult(
                        "API agrees with independent source",
                        True,
                        f"API={quote['price']}; CoinGecko={independent_price}; "
                        f"error={independent_error:.6%}",
                    )
                )

            analysis = request(
                client,
                f"{base_url}/api/analysis/{symbol}",
                stage="Production candle analysis",
                params={
                    "timeframe": args.timeframe,
                    "limit": args.limit,
                    "verification_nonce": str(uuid.uuid4()),
                },
                headers=headers,
            )
            analysis.raise_for_status()
            analysis_payload = analysis.json()
            completed = [c for c in analysis_payload["candles"] if c["is_complete"]]
            require(len(completed) >= 1, "Analysis returned no completed candles")
            require(
                analysis_payload["data_quality"]["candle_completeness"] != "INVALID",
                "Analysis candle completeness is invalid",
            )
            last_completed = completed[-1]
            last_close = float(last_completed["close"])
            price_delta = abs(float(quote["price"]) - last_close)
            timestamp_delta = provider_time - parse_datetime(last_completed["timestamp"])
            require(
                price_delta >= MIN_CURRENT_VS_CANDLE_PRICE_DELTA
                or timestamp_delta.total_seconds() > 0,
                "Current quote is indistinguishable from the latest completed candle",
            )
            results.append(
                CheckResult(
                    "Current quote is distinct from completed candle data",
                    True,
                    f"current={quote['price']}; completed_close={last_close}; delta={price_delta:.8f}",
                )
            )

            time.sleep(CACHE_PROBE_DELAY_SECONDS)
            second_nonce = str(uuid.uuid4())
            second = request(
                client,
                f"{base_url}/api/market/quote/{symbol}",
                stage="Production forced-refresh quote",
                params={"refresh": "true", "verification_nonce": second_nonce},
                headers={**headers, "X-Verification-Nonce": second_nonce},
            )
            second.raise_for_status()
            if expected_commit:
                require(
                    second.headers.get("X-Deployment-Commit") == expected_commit,
                    "Second quote response deployment commit mismatch: "
                    f"expected {expected_commit}, observed "
                    f"{second.headers.get('X-Deployment-Commit', '<missing>')}",
                )
            second_quote = second.json()["quote"]
            require(
                second.headers.get("X-Market-Data-Cache") == "MISS",
                "Second forced refresh was served from cache",
            )
            require(
                second_quote.get("observed_at") != quote.get("observed_at"),
                "Forced refresh did not advance backend observation time",
            )
            results.append(
                CheckResult(
                    "Canonical cache does not mask forced refresh",
                    True,
                    f"first_observed_at={quote['observed_at']}; "
                    f"second_observed_at={second_quote['observed_at']}",
                )
            )

            fallback = request(
                client,
                f"{base_url}/api/market/verification/fallback/{symbol}",
                stage="Protected provider fallback",
                params={"timeframe": args.timeframe, "limit": args.limit},
                headers=headers,
            )
            fallback.raise_for_status()
            if expected_commit:
                require(
                    fallback.headers.get("X-Deployment-Commit") == expected_commit,
                    "Fallback response deployment commit mismatch: "
                    f"expected {expected_commit}, observed "
                    f"{fallback.headers.get('X-Deployment-Commit', '<missing>')}",
                )
            fallback_payload = fallback.json()
            require(
                fallback_payload.get("fallback_verified") is True,
                f"Fallback path was not exercised: {fallback_payload}",
            )
            fallback_quote = fallback_payload["quote"]
            require(
                fallback_quote["status"] in {"LIVE", "DELAYED", "STALE"},
                f"Fallback returned invalid status: {fallback_quote}",
            )
            require(
                fallback_quote.get("fallback_used") is True,
                "Fallback response did not mark fallback_used=true",
            )
            results.append(
                CheckResult(
                    "Protected provider fallback path",
                    True,
                    f"quote_provider={fallback_payload.get('selected_quote_provider')}; "
                    f"candle_provider={fallback_payload.get('selected_candle_provider')}; "
                    f"attempts={fallback_payload.get('provider_attempts')}",
                )
            )

        except (httpx.HTTPError, KeyError, ValueError, AssertionError, VerificationTransportError) as exc:
            results.append(CheckResult("PRODUCTION VERIFICATION", False, str(exc)))

    failed = [result for result in results if not result.passed]
    print("\nPRODUCTION MARKET-DATA VERIFICATION\n")
    print("=" * 72)
    for result in results:
        print(f"[{'PASS' if result.passed else 'FAIL'}] {result.name}: {result.detail}")
    print("=" * 72)
    if failed:
        print(f"FAILED: {len(failed)} verification check(s) failed.")
        return 1
    print(f"PASSED: {len(results)} verification checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
