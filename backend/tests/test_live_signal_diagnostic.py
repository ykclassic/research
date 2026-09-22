import math

from scripts.diagnose_live_signals import (
    _bucket,
    _is_provider_failure,
    _summarize,
    _validate_observational_invariants,
)


def test_live_diagnostic_bucket_boundaries_are_deterministic() -> None:
    assert _bucket(0.39, (0.25, 0.40, 0.50)) == "<0.4"
    assert _bucket(0.40, (0.25, 0.40, 0.50)) == "<0.5"
    assert _bucket(0.50, (0.25, 0.40, 0.50)) == ">=0.5"


def test_live_diagnostic_summary_counts_rejection_reasons() -> None:
    rows = [
        {
            "symbol": "BTC/USDT",
            "http_status": 200,
            "status": "SUCCESS",
            "score": 0.50,
            "confidence": 0.75,
            "risk_reward": 2.0,
            "qualification_status": "REJECTED",
            "qualification_reasons": ["Confidence 75.0% is below the 82.0% minimum."],
            "components": [],
        },
        {
            "symbol": "ETH/USDT",
            "http_status": 200,
            "status": "SUCCESS",
            "score": 0.70,
            "confidence": 0.85,
            "risk_reward": 1.7,
            "qualification_status": "QUALIFIED",
            "qualification_reasons": [],
            "components": [],
        },
        {
            "symbol": "SUI/USDT",
            "http_status": 503,
            "status": "DEGRADED",
            "failure_class": "provider_unavailable",
            "error": {"detail": "All configured market-data providers were unavailable."},
        },
    ]

    summary = _summarize(rows)

    assert summary["successful_pairs"] == 2
    assert summary["http_failures"] == 1
    assert summary["degraded_pairs"] == 1
    assert summary["provider_failures"] == 1
    assert summary["fatal_failures"] == 0
    assert summary["qualified"] == 1
    assert summary["rejected"] == 1
    assert summary["rejection_reasons"]["Confidence 75.0% is below the 82.0% minimum."] == 1


def test_live_diagnostic_rejects_non_fixed_confidence_mapping() -> None:
    rows = [
        {
            "symbol": "BTC/USDT",
            "http_status": 200,
            "score": 0.60,
            "confidence": 0.81,
        }
    ]

    errors = _validate_observational_invariants({"signals": rows})

    assert errors
    assert "BTC/USDT" in errors[0]
    assert math.isclose(0.50 + 0.50 * 0.60, 0.80)


def test_provider_failure_classifier_accepts_provider_exhaustion_detail() -> None:
    result = {
        "http_status": 503,
        "payload": {
            "detail": (
                "SOL/USDT 4h: primary crypto provider timed out; "
                "fallback failed (RuntimeError: All configured market-data providers "
                "were unavailable and no canonical candle cache entry exists.)"
            )
        },
    }

    assert _is_provider_failure(result) is True


def test_provider_failure_classifier_does_not_mask_non_provider_503() -> None:
    result = {
        "http_status": 503,
        "payload": {"detail": "Signal preferences are temporarily unavailable."},
    }

    assert _is_provider_failure(result) is False


def test_live_diagnostic_summary_counts_fatal_endpoint_failures() -> None:
    rows = [
        {
            "symbol": "BTC/USDT",
            "http_status": 503,
            "status": "FATAL",
            "failure_class": "endpoint_failure",
            "error": {"detail": "Signal preferences are temporarily unavailable."},
        }
    ]

    summary = _summarize(rows)

    assert summary["successful_pairs"] == 0
    assert summary["degraded_pairs"] == 0
    assert summary["provider_failures"] == 0
    assert summary["fatal_failures"] == 1
    assert summary["http_failures"] == 1
