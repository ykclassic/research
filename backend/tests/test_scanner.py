from __future__ import annotations

from datetime import datetime, timezone

from app.models.scanner import ScannerConditions
from app.services import scanner


class _Response:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return self._rows


def test_scanner_conditions_require_qualified(monkeypatch):
    class Signal:
        qualification_status = type("Q", (), {"value": "REJECTED"})()
        confidence = 0.95
        risk_reward = 3.0
        regime = "STRONG_TREND_UP"
        signal = type("S", (), {"value": "STRONG_BUY"})()
        market_structure = "BOS"
        mtf_alignment = 4
        momentum = 0.8
        volatility = 0.01

    conditions = ScannerConditions(min_confidence=0.82, require_qualified=True)
    assert scanner._matches(Signal(), 100.0, conditions) is False


def test_scanner_conditions_apply_quality_filters():
    class Signal:
        qualification_status = type("Q", (), {"value": "QUALIFIED"})()
        confidence = 0.90
        risk_reward = 2.0
        regime = "STRONG_TREND_UP"
        signal = type("S", (), {"value": "STRONG_BUY"})()
        market_structure = "BOS"
        mtf_alignment = 4
        momentum = 0.8
        volatility = 0.01

    conditions = ScannerConditions(
        min_confidence=0.82,
        min_risk_reward=1.5,
        regimes=["STRONG_TREND_UP"],
        directions=["STRONG_BUY"],
        structures=["BOS"],
        min_mtf_alignment=3,
        min_momentum=0.5,
        max_volatility=0.02,
        min_volume=50,
    )
    assert scanner._matches(Signal(), 100.0, conditions) is True
    assert scanner._matches(Signal(), 10.0, conditions) is False


def test_historical_evidence_marks_small_samples(monkeypatch):
    monkeypatch.setattr(
        scanner,
        "_request",
        lambda *args, **kwargs: _Response(
            [{"outcome": "TARGET_HIT", "r_result": 2.0, "confidence": 0.9}]
            * 5
        ),
    )
    result = scanner._historical_evidence(
        "token", "user", "BTC/USDT", "1h", "STRONG_TREND_UP", "BOS"
    )
    assert result["sample_size"] == 5
    assert result["sample_sufficient"] is False
    assert result["target_hit_rate"] == 1.0


def test_due_schedule_uses_service_role(monkeypatch):
    scanner.settings.supabase_service_role_key = "service"
    monkeypatch.setattr(
        scanner,
        "_request",
        lambda method, resource, token, params=None, **kwargs: _Response(
            [{"id": "schedule", "user_id": "user", "preset_id": "preset"}]
        ),
    )
    rows = scanner.get_due_schedules()
    assert rows[0]["id"] == "schedule"


def test_scanner_custom_conditions_support_all_and_any():
    class Signal:
        qualification_status = type("Q", (), {"value": "QUALIFIED"})()
        confidence = 0.93
        risk_reward = 2.4
        regime = "TRENDING"
        signal = type("S", (), {"value": "BUY"})()
        market_structure = "BOS_BULLISH"
        mtf_alignment = 4
        momentum = 0.7
        volatility = 0.01
        liquidity_conditions = "SWEEP_LOW"

    all_conditions = ScannerConditions(
        custom_match="ALL",
        custom_conditions=[
            {"field": "confidence", "operator": "gte", "value": 0.9},
            {"field": "risk_reward", "operator": "gte", "value": 2},
            {"field": "liquidity", "operator": "contains", "value": "sweep"},
        ],
    )
    assert scanner._matches(Signal(), 100, all_conditions, "BULLISH") is True

    any_conditions = ScannerConditions(
        custom_match="ANY",
        custom_conditions=[
            {"field": "confidence", "operator": "gte", "value": 0.99},
            {"field": "trend", "operator": "eq", "value": "BULLISH"},
        ],
    )
    assert scanner._matches(Signal(), 100, any_conditions, "BULLISH") is True
