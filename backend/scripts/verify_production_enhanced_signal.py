from __future__ import annotations

import argparse
import os

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the production Enhanced Signal path.")
    parser.add_argument("--base-url", default=os.environ.get("MARKET_API_BASE", "https://research-76vr.onrender.com"))
    parser.add_argument("--symbol", default=os.environ.get("ENHANCED_SIGNAL_SYMBOL", "BTC/USDT"))
    parser.add_argument("--limit", type=int, default=int(os.environ.get("ENHANCED_SIGNAL_LIMIT", "250")))
    parser.add_argument("--oidc-token", default=os.environ.get("GITHUB_OIDC_TOKEN", ""))
    args = parser.parse_args()

    if not args.oidc_token:
        raise SystemExit("FAIL: GITHUB_OIDC_TOKEN is required.")

    url = f"{args.base_url.rstrip('/')}/api/enhanced-signals/verification/{args.symbol}"
    print(f"Verifying production Enhanced Signal: {args.symbol}")
    try:
        response = httpx.get(
            url,
            params={"limit": args.limit},
            headers={"Authorization": f"Bearer {args.oidc_token}"},
            timeout=240.0,
        )
    except httpx.HTTPError as exc:
        raise SystemExit(f"FAIL: Enhanced Signal verification request failed: {type(exc).__name__}") from exc

    if response.status_code != 200:
        detail = response.text[:300].replace("\n", " ")
        raise SystemExit(
            f"FAIL: Enhanced Signal verification returned HTTP {response.status_code}: {detail}"
        )

    payload = response.json()
    expected = {"status", "symbol", "timeframes", "sources", "cache_hits", "qualification_status"}
    missing = sorted(expected - set(payload))
    if missing:
        raise SystemExit(f"FAIL: Enhanced Signal verification response is missing: {', '.join(missing)}")

    expected_timeframes = {"1d", "4h", "1h", "15m", "5m"}
    actual_timeframes = set(payload["timeframes"])
    if actual_timeframes != expected_timeframes:
        raise SystemExit(
            f"FAIL: Enhanced Signal timeframes mismatch: {sorted(actual_timeframes)}"
        )

    if payload["status"] != "ok":
        raise SystemExit("FAIL: Enhanced Signal verification did not return status=ok.")

    print("PASS: production Enhanced Signal acquisition and generation path is healthy.")
    print(f"  symbol={payload['symbol']}")
    print(f"  qualification_status={payload['qualification_status']}")
    print(f"  sources={payload['sources']}")
    print(f"  cache_hits={payload['cache_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
