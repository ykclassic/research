#!/usr/bin/env python3
"""Run a non-gating live diagnostic across the configured crypto signal universe.

This diagnostic is deliberately observational: it never changes signal preferences,
searches for a better threshold, or fits parameters to the current observations.
It records pair-level qualification reasons, score components, provider/source data,
and distribution summaries so threshold decisions can be made on independent
historical holdouts rather than today's live sample.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

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


PROVIDER_FAILURE_MARKERS = (
    "all configured market-data providers were unavailable",
    "primary crypto provider timed out",
    "primary crypto provider failed",
    "kraken cross-provider failed",
    "candle provider exceeded the",
)


def _is_provider_failure(result: dict) -> bool:
    """Return True only for a signal endpoint failure caused by market providers.

    The production MTF and market-data verification steps are the gating checks
    for canonical data health. This diagnostic is observational, so a signal
    request that fails because every upstream provider is unavailable should be
    recorded as degraded rather than turning the whole workflow red. Other
    endpoint failures (auth, preferences, application errors, connectivity) remain
    fatal and must continue to fail the workflow.
    """
    if result.get("http_status") != 503:
        return False
    payload = result.get("payload")
    if not isinstance(payload, dict):
        return False
    detail = str(payload.get("detail", "")).lower()
    return any(marker in detail for marker in PROVIDER_FAILURE_MARKERS)


def _bucket(value: float, boundaries: tuple[float, ...]) -> str:
    for upper in boundaries:
        if value < upper:
            return f"<{upper:g}"
    return f">={boundaries[-1]:g}"


def _summarize(rows: list[dict]) -> dict:
    successful = [row for row in rows if row.get("status") == "SUCCESS"]
    provider_failures = [row for row in rows if row.get("status") == "DEGRADED"]
    fatal_failures = [row for row in rows if row.get("status") == "FATAL"]
    rejection_reasons = Counter(
        reason
        for row in successful
        if row.get("qualification_status") == "REJECTED"
        for reason in row.get("qualification_reasons", [])
    )
    score_buckets = Counter(
        _bucket(abs(float(row["score"])), (0.25, 0.40, 0.50, 0.60, 0.64, 0.65, 0.80, 0.90))
        for row in successful
    )
    confidence_buckets = Counter(
        _bucket(float(row["confidence"]), (0.65, 0.70, 0.75, 0.80, 0.82, 0.85, 0.90, 0.95))
        for row in successful
    )
    rr_buckets = Counter(
        _bucket(float(row["risk_reward"]), (1.0, 1.5, 2.0, 3.0, 5.0))
        for row in successful
    )
    component_summary: dict[str, dict[str, float]] = {}
    for timeframe in ("1d", "4h", "1h", "15m"):
        components = [
            component
            for row in successful
            for component in row.get("components", [])
            if component.get("timeframe") == timeframe
        ]
        if not components:
            continue
        component_summary[timeframe] = {
            "count": float(len(components)),
            "mean_indicator_score": sum(float(item["indicator_score"]) for item in components) / len(components),
            "mean_smc_score": sum(float(item["smc_score"]) for item in components) / len(components),
            "mean_combined_score": sum(float(item["combined_score"]) for item in components) / len(components),
        }

    return {
        "successful_pairs": len(successful),
        "degraded_pairs": len(provider_failures),
        "provider_failures": len(provider_failures),
        "fatal_failures": len(fatal_failures),
        "http_failures": len(provider_failures) + len(fatal_failures),
        "qualified": sum(row.get("qualification_status") == "QUALIFIED" for row in successful),
        "rejected": sum(row.get("qualification_status") == "REJECTED" for row in successful),
        "score_magnitude_buckets": dict(sorted(score_buckets.items())),
        "confidence_buckets": dict(sorted(confidence_buckets.items())),
        "risk_reward_buckets": dict(sorted(rr_buckets.items())),
        "rejection_reasons": dict(rejection_reasons.most_common()),
        "component_summary": component_summary,
    }


def _validate_observational_invariants(report: dict) -> list[str]:
    errors: list[str] = []
    for row in report["signals"]:
        if row.get("http_status") != 200:
            continue
        score = row.get("score")
        confidence = row.get("confidence")
        if not isinstance(score, (int, float)) or not isinstance(confidence, (int, float)):
            errors.append(f"{row['symbol']}: missing numeric score/confidence")
            continue
        expected = min(1.0, 0.50 + 0.50 * abs(float(score)))
        if not math.isclose(float(confidence), expected, rel_tol=0.0, abs_tol=1e-9):
            errors.append(
                f"{row['symbol']}: confidence {confidence} does not match fixed score mapping {expected}"
            )
    return errors


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
        "methodology": {
            "threshold_tuning": False,
            "parameter_fitting": False,
            "uses_current_live_sample_for_threshold_selection": False,
            "confidence_is_calibrated_probability": False,
            "note": "Use audit_signal_calibration.py with chronological labeled outcomes for walk-forward calibration; do not tune thresholds on this live sample.",
        },
        "signals": [],
    }
    failures = 0

    for symbol in CRYPTO_PAIRS:
        try:
            result = fetch_signal(args.base_url, symbol, args.limit, args.oidc_token or None)
            payload = result["payload"]
            if result["http_status"] >= 400:
                provider_failure = _is_provider_failure(result)
                if not provider_failure:
                    failures += 1
                row = {
                    "symbol": symbol,
                    "http_status": result["http_status"],
                    "status": "DEGRADED" if provider_failure else "FATAL",
                    "failure_class": "provider_unavailable" if provider_failure else "endpoint_failure",
                    "error": payload,
                }
                report["signals"].append(row)
                label = "DEGRADED provider availability" if provider_failure else "FATAL endpoint failure"
                print(f"{symbol}: {label} HTTP {result['http_status']} {payload}")
                continue

            components = payload.get("components", [])
            row = {
                "symbol": symbol,
                "http_status": result["http_status"],
                "status": "SUCCESS",
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
            row = {
                "symbol": symbol,
                "status": "FATAL",
                "failure_class": "connectivity_or_client_error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            report["signals"].append(row)
            print(f"{symbol}: FATAL {row['error']}")

    report["summary"] = _summarize(report["signals"])
    report["invariant_errors"] = _validate_observational_invariants(report)

    print("\nLIVE SIGNAL DIAGNOSTIC SUMMARY")
    print(json.dumps(report["summary"], indent=2))
    if report["invariant_errors"]:
        print("\nINVARIANT ERRORS")
        for error in report["invariant_errors"]:
            print(f"  {error}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)

    return 1 if failures or report["invariant_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
