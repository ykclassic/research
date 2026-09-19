#!/usr/bin/env python3
"""Run a non-gating live diagnostic across the configured crypto signal universe.

The diagnostic records the deterministic score, heuristic confidence, RR, per-timeframe
components, and qualification reasons without changing signal preferences. It is intended
for observability/calibration, not threshold tuning.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.symbols import CRYPTO_PAIRS


def fetch_signal(base_url: str, symbol: str, limit: int, oidc_token: str | None = None) -> dict:
    url = f"{base_url.rstrip('/')}/api/signals/{symbol.replace('/', '%2F')}?limit={limit}"
    headers = {"Accept": "application/json"}
    if oidc_token:
        headers["Authorization"] = f"Bearer {oidc_token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"http_status": response.status, "url": url, "payload": payload}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw_error_body": body}
        return {"http_status": exc.code, "url": url, "payload": payload}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://research-76vr.onrender.com")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--output", default="")
    parser.add_argument("--oidc-token", default="")
    args = parser.parse_args()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "limit": args.limit,
        "signals": [],
    }
    failures = 0

    for symbol in CRYPTO_PAIRS:
        try:
            result = fetch_signal(args.base_url, symbol, args.limit, args.oidc_token or None)
            payload = result["payload"]
            if result["http_status"] >= 400:
                failures += 1
                row = {
                    "symbol": symbol,
                    "http_status": result["http_status"],
                    "error": payload,
                }
                report["signals"].append(row)
                print(f"{symbol}: HTTP {result['http_status']} {payload}")
                continue
            components = payload.get("components", [])
            row = {
                "symbol": symbol,
                "http_status": result["http_status"],
                "signal": payload.get("signal"),
                "score": payload.get("score"),
                "confidence": payload.get("confidence"),
                "risk_reward": payload.get("risk_reward"),
                "source": payload.get("source"),
                "latest_candle_timestamp": payload.get("latest_candle_timestamp"),
                "qualification_status": payload.get("qualification_status"),
                "qualification_reasons": payload.get("qualification_reasons", []),
                "components": [
                    {
                        "timeframe": item.get("timeframe"),
                        "indicator_score": item.get("indicator_score"),
                        "smc_score": item.get("smc_score"),
                        "combined_score": item.get("combined_score"),
                    }
                    for item in components
                ],
            }
            report["signals"].append(row)
            print(
                f"{symbol}: {row['qualification_status']} "
                f"signal={row['signal']} score={row['score']} "
                f"confidence={row['confidence']} RR={row['risk_reward']}"
            )
            for reason in row["qualification_reasons"]:
                print(f"  reason: {reason}")
            for component in row["components"]:
                print(
                    f"  {component['timeframe']}: "
                    f"indicator={component['indicator_score']:.4f} "
                    f"smc={component['smc_score']:.4f} "
                    f"combined={component['combined_score']:.4f}"
                )
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            failures += 1
            row = {"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}
            report["signals"].append(row)
            print(f"{symbol}: ERROR {row['error']}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
