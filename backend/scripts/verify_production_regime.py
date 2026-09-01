from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("REGIME_API_BASE", "https://research-76vr.onrender.com").rstrip("/")
SYMBOL = os.getenv("REGIME_SYMBOL", "BTC/USD")
TIMEFRAME = os.getenv("REGIME_TIMEFRAME", "1h")
LIMIT = int(os.getenv("REGIME_LIMIT", "250"))
PUBLICATION_TOLERANCE_SECONDS = int(os.getenv("REGIME_PUBLICATION_TOLERANCE", "180"))
OIDC_TOKEN = os.getenv("GITHUB_OIDC_TOKEN", "")
EXPECTED_SOURCE = os.getenv("REGIME_EXPECTED_SOURCE", "twelve_data")

TIMEFRAME_SECONDS = {
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def get_json(path: str, *, authorization: str | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = f"Bearer {authorization}"
    request = Request(f"{BASE_URL}{path}", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=45) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"detail": str(exc)}
        return exc.code, body
    except (URLError, TimeoutError) as exc:
        fail(f"API request failed: {exc}")
    return 0, {}


def parse_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field_name} is missing or null; production regime freshness metadata is mandatory")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"{field_name} is not a valid ISO-8601 timestamp: {value!r}")
        raise AssertionError from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{field_name} is not timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def main() -> int:
    print("PRODUCTION MARKET-REGIME VERIFICATION")
    print("=" * 72)

    if TIMEFRAME not in TIMEFRAME_SECONDS:
        fail(f"Unsupported verification timeframe: {TIMEFRAME}")
    if not OIDC_TOKEN:
        fail("GITHUB_OIDC_TOKEN is required for production verification")

    encoded_symbol = SYMBOL.replace("/", "%2F")
    path = f"/api/regime/{encoded_symbol}?timeframe={TIMEFRAME}&limit={LIMIT}"

    status, _ = get_json(path)
    if status != 401:
        fail(f"Authentication gate failed: unauthenticated request returned HTTP {status}")
    print("[PASS] API authentication gate: unauthenticated regime request rejected with HTTP 401")

    status, body = get_json(path, authorization=OIDC_TOKEN)
    if status != 200:
        fail(f"Authenticated regime API failed: HTTP {status}; body={body}")
    print(f"[PASS] API reachable: HTTP 200; endpoint={BASE_URL}{path}")

    required = {
        "symbol",
        "timeframe",
        "source",
        "provider_timestamp",
        "latest_candle_timestamp",
        "candle_count",
        "regime",
        "confidence",
        "evidence",
        "thresholds",
        "rule_id",
        "rule",
    }
    missing = sorted(required - body.keys())
    if missing:
        fail(f"Regime contract missing fields: {missing}")

    if body["symbol"] != SYMBOL or body["timeframe"] != TIMEFRAME:
        fail("API returned a symbol/timeframe different from the request")
    if body["source"] != EXPECTED_SOURCE:
        fail(f"Regime source is {body['source']!r}; expected {EXPECTED_SOURCE!r}")
    print(f"[PASS] API integration: deterministic regime result is sourced from {body['source']}")

    provider_timestamp = parse_timestamp(body["provider_timestamp"], "provider_timestamp")
    latest_candle_timestamp = parse_timestamp(
        body["latest_candle_timestamp"], "latest_candle_timestamp"
    )
    now = datetime.now(timezone.utc)
    provider_age = (now - provider_timestamp).total_seconds()
    max_age = TIMEFRAME_SECONDS[TIMEFRAME] + PUBLICATION_TOLERANCE_SECONDS
    if provider_age < 0:
        fail(f"Provider timestamp is in the future by {-provider_age:.2f}s")
    if provider_age > max_age:
        fail(f"Regime provider data is stale: age={provider_age:.2f}s > SLA {max_age}s")
    if latest_candle_timestamp > provider_timestamp:
        fail("Latest completed candle timestamp is newer than provider timestamp")
    print(
        f"[PASS] Provider freshness: age={provider_age:.2f}s <= SLA {max_age}s "
        f"({TIMEFRAME} interval + {PUBLICATION_TOLERANCE_SECONDS}s tolerance)"
    )

    if body["candle_count"] < 220:
        fail(f"Insufficient completed candles: {body['candle_count']}")
    if body["confidence"] < 0 or body["confidence"] > 1:
        fail(f"Confidence outside [0,1]: {body['confidence']}")
    if body["regime"] not in {
        "STRONG_TREND_UP",
        "STRONG_TREND_DOWN",
        "WEAK_TREND",
        "RANGE",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "UNKNOWN",
    }:
        fail(f"Invalid regime label: {body['regime']}")
    print(
        f"[PASS] Regime contract: label={body['regime']}; "
        f"confidence={body['confidence']:.6f}; candles={body['candle_count']}"
    )

    evidence = body["evidence"]
    thresholds = body["thresholds"]
    for field in (
        "adx",
        "atr",
        "atr_percentile",
        "bb_width",
        "bb_width_percentile",
        "trend_persistence",
        "directional_move_ratio",
    ):
        if evidence.get(field) is not None and not isinstance(evidence[field], (int, float)):
            fail(f"Evidence field {field} is not numeric")
    if thresholds != {
        "adx_strong": 25.0,
        "persistence_strong": 0.70,
        "persistence_weak": 0.50,
        "directional_ratio_strong": 0.55,
        "directional_ratio_weak": 0.25,
        "volatility_high_percentile": 0.80,
        "volatility_low_percentile": 0.20,
    }:
        fail(f"Unexpected production threshold contract: {thresholds}")
    print(
        f"[PASS] Evidence contract: rule={body['rule_id']}; "
        "all reported thresholds are explicit and version-stable"
    )

    print("=" * 72)
    print("PASS: 6 production regime verification checks completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
