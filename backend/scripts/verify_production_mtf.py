from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


API_BASE = os.getenv("MARKET_API_BASE", "https://research-76vr.onrender.com").rstrip("/")
SYMBOL = os.getenv("MARKET_SYMBOL", "BTC/USD").upper()
LIMIT = int(os.getenv("MARKET_ANALYSIS_LIMIT", "250"))
MAX_EXTRA_AGE_SECONDS = float(os.getenv("MTF_MAX_EXTRA_AGE_SECONDS", "180"))
# These values must match the backend Timeframe enum exactly.
EXPECTED_TIMEFRAMES = {"1d", "4h", "1h", "15m"}
# Crypto MTF analysis now uses the credential-free Kraken public provider as
# its primary source, with the legacy providers retained as fallback paths.
APPROVED_PROVIDERS = {"kraken_public", "twelve_data", "finnhub", "alpha_vantage"}
DURATION_BY_TIMEFRAME = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is not timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def completed_candle_age_seconds(timestamp: datetime, timeframe: str, now: datetime) -> float:
    """Return age from the *close* of the completed candle, not its open.

    Provider candle timestamps identify the candle's opening instant. A daily
    candle stamped 00:00 is therefore only a few hours old shortly after the
    next midnight, even though its opening timestamp is more than 24 hours
    old. Production freshness must use the completed candle close.
    """
    duration = timedelta(seconds=DURATION_BY_TIMEFRAME[timeframe])
    close_at = timestamp + duration
    return (now - close_at).total_seconds()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    token = os.getenv("GITHUB_OIDC_TOKEN", "").strip()
    if not token:
        print("FAIL: GITHUB_OIDC_TOKEN is required.", file=sys.stderr)
        return 2

    headers = {
        "Authorization": f"Bearer {token}",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    }
    url = f"{API_BASE}/api/mtf/{SYMBOL}"
    try:
        with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True) as client:
            response = client.get(url, params={"limit": LIMIT}, headers=headers)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        rows = payload.get("timeframes")
        require(isinstance(rows, list), f"MTF response has no timeframes list: {payload}")
        observed = {str(row.get("timeframe")) for row in rows}
        require(observed == EXPECTED_TIMEFRAMES, f"Expected {EXPECTED_TIMEFRAMES}, observed {observed}")
        require(len(rows) == 4, f"Expected four timeframe analyses, observed {len(rows)}")

        now = datetime.now(timezone.utc)
        for row in rows:
            timeframe = str(row["timeframe"])
            source = str(row["source"])
            timestamp = parse_timestamp(str(row["latest_candle_timestamp"]))
            count = int(row["candle_count"])
            age = completed_candle_age_seconds(timestamp, timeframe, now)
            require(source in APPROVED_PROVIDERS, f"{timeframe}: unexpected provider {source}")
            require(count >= 30, f"{timeframe}: insufficient candle count {count}")
            require(age >= -5, f"{timeframe}: latest completed candle closes in {-age:.1f}s")
            require(age <= DURATION_BY_TIMEFRAME[timeframe] + MAX_EXTRA_AGE_SECONDS, f"{timeframe}: latest completed candle age {age:.1f}s exceeds {DURATION_BY_TIMEFRAME[timeframe] + MAX_EXTRA_AGE_SECONDS:.0f}s")
            print(f"PASS {timeframe}: provider={source}; latest_completed={timestamp.isoformat()}; close_age={age:.1f}s; candles={count}")

        require(payload.get("symbol") == SYMBOL, f"MTF symbol mismatch: {payload.get('symbol')}")
        print(f"PASS MTF: {SYMBOL} Daily/H4/H1/M15 are current completed-candle datasets.")
        return 0
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AssertionError) as exc:
        print(f"FAIL MTF verification: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
