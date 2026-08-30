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
# Twelve Data documents typical REST candle publication latency of roughly
# 0.3-2 minutes depending on the instrument. The backend already exposes a
# 180-second stale-quote boundary, so production verification uses the same
# provider freshness contract rather than an incompatible 120-second limit.
MAX_PROVIDER_AGE_SECONDS = 180.0
MAX_BACKEND_OBSERVATION_AGE_SECONDS = 15.0
MAX_INDEPENDENT_SOURCE_AGE_SECONDS = 180.0
MAX_FUTURE_TIMESTAMP_SKEW_SECONDS = 5.0
MIN_CURRENT_VS_CANDLE_PRICE_DELTA = 0.01
CACHE_PROBE_DELAY_SECONDS = 1.25
REQUEST_TIMEOUT_SECONDS = 30.0
REQUEST_CONNECT_TIMEOUT_SECONDS = 10.0
REQUEST_RETRIES = 2
REQUEST_RETRY_DELAYS_SECONDS = (1.0, 3.0)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp is not timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def relative_error(actual: float, reference: float) -> float:
    if reference <= 0:
        raise ValueError("Reference price must be positive.")
    return abs(actual - reference) / reference


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    operation: str = "HTTP request",
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(REQUEST_RETRIES + 1):
        try:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            last_error = exc
            if attempt >= REQUEST_RETRIES:
                raise RuntimeError(
                    f"{operation} timed out after {REQUEST_RETRIES + 1} attempts "
                    f"(read={REQUEST_TIMEOUT_SECONDS:.0f}s, connect={REQUEST_CONNECT_TIMEOUT_SECONDS:.0f}s)."
                ) from exc
            time.sleep(REQUEST_RETRY_DELAYS_SECONDS[attempt])
        except httpx.HTTPError:
            raise
    raise RuntimeError(f"{operation} failed: {last_error}")


def verify_health(client: httpx.Client, base_url: str) -> CheckResult:
    started = time.perf_counter()
    response = request_json(client, f"{base_url}/health", operation="Production health check")
    elapsed_ms = (time.perf_counter() - started) * 1000
    payload = response.json()
    require(payload.get("ok") is True, f"health payload is not healthy: {payload}")
    return CheckResult(
        "API reachable",
        True,
        f"HTTP 200 in {elapsed_ms:.0f} ms; service={payload.get('service')}; environment={payload.get('environment')}",
    )


def get_api_quote(
    client: httpx.Client,
    base_url: str,
    symbol: str,
    oidc_token: str,
    *,
    nonce: str,
) -> httpx.Response:
    return request_json(
        client,
        f"{base_url}/api/market/quote/{symbol}",
        params={"refresh": "true", "verification_nonce": nonce},
        headers={
            "Authorization": f"Bearer {oidc_token}",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Verification-Nonce": nonce,
        },
        operation="Deployed market quote",
    )


def get_direct_twelve_data(
    client: httpx.Client,
    api_key: str,
    symbol: str,
) -> dict[str, Any]:
    response = request_json(
        client,
        "https://api.twelvedata.com/quote",
        params={"symbol": symbol, "apikey": api_key, "interval": "1min"},
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
        operation="Direct Twelve Data quote",
    )
    payload = response.json()
    if "code" in payload or ("message" in payload and "close" not in payload):
        raise RuntimeError(f"Twelve Data error: {payload}")
    return payload


def get_independent_coin_gecko(client: httpx.Client) -> dict[str, Any]:
    response = request_json(
        client,
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": "bitcoin",
            "vs_currencies": "usd",
            "include_last_updated_at": "true",
        },
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
        operation="CoinGecko verification quote",
    )
    payload = response.json()
    bitcoin = payload.get("bitcoin")
    require(isinstance(bitcoin, dict), f"CoinGecko response missing bitcoin data: {payload}")
    return bitcoin


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Production verification for the deployed market-data API."
    )
    parser.add_argument("--api-base", default=os.getenv("MARKET_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--symbol", default=os.getenv("MARKET_SYMBOL", DEFAULT_SYMBOL))
    parser.add_argument("--timeframe", default=os.getenv("MARKET_TIMEFRAME", DEFAULT_TIMEFRAME))
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("MARKET_ANALYSIS_LIMIT", DEFAULT_ANALYSIS_LIMIT)),
    )
    parser.add_argument("--provider-tolerance", type=float, default=DIRECT_PROVIDER_TOLERANCE)
    parser.add_argument(
        "--independent-tolerance",
        type=float,
        default=INDEPENDENT_SOURCE_TOLERANCE,
    )
    parser.add_argument(
        "--max-provider-age",
        type=float,
        default=float(os.getenv("MARKET_MAX_PROVIDER_AGE", MAX_PROVIDER_AGE_SECONDS)),
    )
    parser.add_argument(
        "--max-observation-age",
        type=float,
        default=MAX_BACKEND_OBSERVATION_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-independent-age",
        type=float,
        default=MAX_INDEPENDENT_SOURCE_AGE_SECONDS,
    )
    args = parser.parse_args()

    require(args.max_provider_age > 0, "Provider freshness SLA must be greater than zero.")

    oidc_token = os.getenv("GITHUB_OIDC_TOKEN")
    twelve_data_key = os.getenv("TWELVE_DATA_API_KEY")
    if not oidc_token:
        print(
            "FAIL: GITHUB_OIDC_TOKEN is required for protected production verification.",
            file=sys.stderr,
        )
        return 2
    if not twelve_data_key:
        print(
            "FAIL: TWELVE_DATA_API_KEY is required for direct provider verification.",
            file=sys.stderr,
        )
        return 2

    base_url = args.api_base.rstrip("/")
    symbol = args.symbol.upper()
    results: list[CheckResult] = []
    timeout = httpx.Timeout(
        REQUEST_TIMEOUT_SECONDS,
        connect=REQUEST_CONNECT_TIMEOUT_SECONDS,
    )

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        try:
            results.append(verify_health(client, base_url))

            first_nonce = str(uuid.uuid4())
            first_response = get_api_quote(
                client,
                base_url,
                symbol,
                oidc_token,
                nonce=first_nonce,
            )
            first = first_response.json()
            quote1 = first["quote"]

            require(quote1["status"] == "LIVE", f"API quote is not LIVE: {quote1}")
            require(
                quote1["source"] == "twelve_data",
                f"API source is not Twelve Data: {quote1}",
            )
            require(
                first_response.headers.get("X-Market-Data-Source") == "twelve_data",
                "API source header is not twelve_data",
            )
            require(
                first_response.headers.get("X-Market-Data-Refresh") == "true",
                "API did not acknowledge refresh=true",
            )
            require(
                "no-store" in first_response.headers.get("Cache-Control", "").lower(),
                "API response is not marked no-store",
            )
            require(
                first_response.headers.get("X-Market-Data-Cache") == "MISS",
                "Refresh request was not a backend cache miss/bypass",
            )
            results.append(
                CheckResult(
                    "Deployed API owns the returned price",
                    True,
                    f"Direct GET to {base_url}; frontend URL was never used; "
                    f"source={quote1['source']}; OIDC-authenticated request",
                )
            )

            observed_at = parse_datetime(quote1["observed_at"])
            provider_timestamp = quote1.get("provider_timestamp")
            require(
                provider_timestamp,
                "Deployed API response did not contain provider_timestamp",
            )
            provider_time = parse_datetime(provider_timestamp)
            now = utc_now()
            observation_age = (now - observed_at).total_seconds()
            provider_age = (now - provider_time).total_seconds()
            require(
                -MAX_FUTURE_TIMESTAMP_SKEW_SECONDS
                <= observation_age
                <= args.max_observation_age,
                f"Backend observation age is {observation_age:.2f}s",
            )
            require(
                -MAX_FUTURE_TIMESTAMP_SKEW_SECONDS
                <= provider_age
                <= args.max_provider_age,
                f"Provider quote age is {provider_age:.2f}s",
            )

            results.append(
                CheckResult(
                    "Fresh timestamps",
                    True,
                    f"provider_timestamp={provider_time.isoformat()} age={provider_age:.2f}s "
                    f"<= SLA {args.max_provider_age:.0f}s; "
                    f"observed_at={observed_at.isoformat()} age={observation_age:.2f}s",
                )
            )

            direct_twelve = get_direct_twelve_data(client, twelve_data_key, symbol)
            direct_price_raw = direct_twelve.get("close", direct_twelve.get("price"))
            require(direct_price_raw is not None, "Direct Twelve Data response has no price")
            direct_price = float(direct_price_raw)
            api_price = float(quote1["price"])
            provider_error = relative_error(api_price, direct_price)
            require(
                provider_error <= args.provider_tolerance,
                f"API vs direct Twelve Data error {provider_error:.6%}",
            )

            direct_timestamp_raw = direct_twelve.get("last_update_at")
            if direct_timestamp_raw is None:
                direct_timestamp_raw = direct_twelve.get("timestamp")
            require(
                direct_timestamp_raw is not None,
                "Direct Twelve Data response has no authoritative timestamp",
            )
            if isinstance(direct_timestamp_raw, (int, float)) or str(
                direct_timestamp_raw
            ).strip().isdigit():
                direct_provider_time = datetime.fromtimestamp(
                    float(direct_timestamp_raw),
                    tz=timezone.utc,
                )
            else:
                direct_provider_time = parse_datetime(str(direct_timestamp_raw))
            direct_provider_age = (utc_now() - direct_provider_time).total_seconds()
            require(
                -MAX_FUTURE_TIMESTAMP_SKEW_SECONDS
                <= direct_provider_age
                <= args.max_provider_age,
                f"Direct Twelve Data quote age is {direct_provider_age:.2f}s",
            )
            require(
                abs((provider_time - direct_provider_time).total_seconds()) <= 120,
                "Deployed provider timestamp materially disagrees with direct Twelve Data timestamp",
            )

            results.append(
                CheckResult(
                    "API agrees with Twelve Data",
                    True,
                    f"API=${api_price:.8f}; direct Twelve Data=${direct_price:.8f}; "
                    f"error={provider_error:.6%} <= {args.provider_tolerance:.2%}; "
                    f"direct_provider_age={direct_provider_age:.2f}s",
                )
            )

            independent = get_independent_coin_gecko(client)
            independent_price = float(independent["usd"])
            independent_error = relative_error(api_price, independent_price)
            require(
                "last_updated_at" in independent,
                "CoinGecko response has no last_updated_at timestamp",
            )
            independent_timestamp = datetime.fromtimestamp(
                float(independent["last_updated_at"]),
                tz=timezone.utc,
            )
            independent_age = (utc_now() - independent_timestamp).total_seconds()
            require(
                independent_error <= args.independent_tolerance,
                f"API vs CoinGecko error {independent_error:.6%}",
            )
            require(
                -MAX_FUTURE_TIMESTAMP_SKEW_SECONDS
                <= independent_age
                <= args.max_independent_age,
                f"CoinGecko verification data is stale: {independent_age:.2f}s",
            )
            results.append(
                CheckResult(
                    "API agrees with independent source",
                    True,
                    f"API=${api_price:.8f}; CoinGecko=${independent_price:.8f}; "
                    f"error={independent_error:.6%} <= {args.independent_tolerance:.2%}; "
                    f"independent_age={independent_age:.2f}s",
                )
            )

            analysis_response = request_json(
                client,
                f"{base_url}/api/analysis/{symbol}",
                params={
                    "timeframe": args.timeframe,
                    "limit": args.limit,
                    "verification_nonce": str(uuid.uuid4()),
                },
                headers={
                    "Authorization": f"Bearer {oidc_token}",
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache",
                },
                operation="Deployed analysis request",
            )
            analysis = analysis_response.json()
            completed = [c for c in analysis["candles"] if c["is_complete"]]
            require(completed, "Analysis returned no completed candles")
            last_completed = completed[-1]
            last_close = float(last_completed["close"])
            price_delta = abs(api_price - last_close)
            timestamp_delta = provider_time - parse_datetime(last_completed["timestamp"])
            require(
                price_delta >= MIN_CURRENT_VS_CANDLE_PRICE_DELTA
                or timestamp_delta.total_seconds() > 0,
                "Current quote is indistinguishable from the latest completed candle "
                "in both price and time",
            )
            results.append(
                CheckResult(
                    "Current quote is distinct from last completed candle",
                    True,
                    f"current=${api_price:.8f}; last_completed_close=${last_close:.8f}; "
                    f"price_delta=${price_delta:.8f}; "
                    f"quote_vs_candle_time_delta={timestamp_delta.total_seconds():.0f}s",
                )
            )

            time.sleep(CACHE_PROBE_DELAY_SECONDS)
            second_nonce = str(uuid.uuid4())
            second_response = get_api_quote(
                client,
                base_url,
                symbol,
                oidc_token,
                nonce=second_nonce,
            )
            quote2 = second_response.json()["quote"]
            require(
                second_response.headers.get("X-Market-Data-Cache") == "MISS",
                "Second refresh request was served from application cache",
            )
            require(
                "no-store" in second_response.headers.get("Cache-Control", "").lower(),
                "Second response is not no-store",
            )
            observed2 = parse_datetime(quote2["observed_at"])
            require(
                observed2 > observed_at,
                "Second forced-refresh observation timestamp did not advance",
            )
            results.append(
                CheckResult(
                    "No stale cached response",
                    True,
                    f"forced refreshes reported MISS; observed_at advanced from "
                    f"{observed_at.isoformat()} to {observed2.isoformat()}",
                )
            )

        except (
            AssertionError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            httpx.HTTPError,
        ) as exc:
            print("FAILED: 1 verification check(s) failed.")
            print("\nPRODUCTION MARKET-DATA VERIFICATION\n")
            print("=" * 72)
            for result in results:
                status = "PASS" if result.passed else "FAIL"
                print(f"[{status}] {result.name}: {result.detail}")
            print(f"[FAIL] PRODUCTION VERIFICATION: {exc}")
            print("=" * 72)
            return 1

    print("\nPRODUCTION MARKET-DATA VERIFICATION\n")
    print("=" * 72)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")
    print("=" * 72)
    print(f"PASS: {len(results)} verification checks completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
