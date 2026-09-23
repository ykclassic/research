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


def test_due_schedule_claim_is_conditional(monkeypatch):
    scanner.settings.supabase_service_role_key = "service"
    calls = []

    class Response:
        def json(self):
            return [{"id": "schedule"}]

    def fake_request(method, resource, token, params=None, **kwargs):
        calls.append((method, resource, token, params, kwargs))
        return Response()

    monkeypatch.setattr(scanner, "_request", fake_request)
    claimed = scanner._claim_due_schedule(
        {"id": "schedule", "interval_minutes": 15},
        datetime.now(timezone.utc),
    )
    assert claimed is True
    assert calls[0][0:3] == ("PATCH", "scanner_schedules", "service")
    assert calls[0][3]["next_run_at"].startswith("lte.")
    assert calls[0][4]["json"]["next_run_at"]


def test_update_schedule_resets_next_run_when_interval_changes(monkeypatch):
    captured = {}

    class Response:
        def json(self):
            return [{
                "id": "schedule",
                "user_id": "user",
                "preset_id": "preset",
                "name": "Hourly",
                "interval_minutes": 60,
                "enabled": True,
                "next_run_at": datetime.now(timezone.utc).isoformat(),
                "last_run_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }]

    def fake_request(method, resource, token, params=None, json=None, **kwargs):
        captured["json"] = json
        return Response()

    monkeypatch.setattr(scanner, "_request", fake_request)
    result = scanner.update_schedule(
        "token",
        "user",
        "schedule",
        scanner.ScannerSchedulePatch(interval_minutes=60),
    )
    assert result.interval_minutes == 60
    assert captured["json"]["interval_minutes"] == 60
    assert captured["json"]["next_run_at"]


def test_in_app_delivery_is_recorded_separately_from_email(monkeypatch):
    requests = []

    class Response:
        def json(self):
            return [{"id": "alert"}]

    def fake_request(method, resource, token, params=None, json=None, **kwargs):
        requests.append((method, resource, json, kwargs))
        if resource == "scanner_opportunities":
            return _Response([])
        if resource == "scanner_alert_events":
            return Response()
        return Response()

    monkeypatch.setattr(scanner, "_request", fake_request)
    monkeypatch.setattr(scanner, "deliver_scanner_alert", lambda *args: "SKIPPED")

    preset = type("Preset", (), {
        "alert_events": ["NEW_QUALIFIED_SIGNAL"],
        "id": "preset",
    })()
    opportunity = type("Opportunity", (), {
        "symbol": "BTC/USDT",
        "observed_at": datetime.now(timezone.utc),
        "direction": "BUY",
        "confidence": 0.9,
        "regime": "TRENDING",
        "setup": "TREND",
        "volatility": 0.01,
        "liquidity": "NONE",
        "last_price": 100.0,
        "target_price": 110.0,
        "stop_loss": 90.0,
        "structural_conditions": {},
        "historical_evidence": {},
        "signal_status": "QUALIFIED",
    })()
    opportunity.model_dump = lambda mode=None: {}

    scanner._emit_intelligent_events("token", "user", preset, opportunity, "opportunity")
    delivery_channels = [
        item[2]["channel"] for item in requests
        if item[1] == "scanner_alert_deliveries"
    ]
    assert "WEB" in delivery_channels
    assert "EMAIL" in delivery_channels
