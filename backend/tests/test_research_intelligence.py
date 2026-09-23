from datetime import datetime, timezone

from app.models.research_intelligence import ResearchSnapshot
from app.services.research_intelligence import compare


def snapshot(state):
    return ResearchSnapshot(
        id="id",
        symbol="BTC/USD",
        snapshot_type="REPORT",
        snapshot_at=datetime.now(timezone.utc),
        state=state,
        engine_version="research-intelligence-v1",
    )


def test_compare_reports_regime_structure_momentum_volatility_and_events():
    before = snapshot({
        "price": 100,
        "trend": "UP",
        "momentum": "POSITIVE",
        "volatility_percent": 2,
        "support": 95,
        "market_regime": "RANGE",
        "technical_structure": "BULLISH",
        "fundamental": {"news_count": 1, "event_count": 0},
        "signal": {"status": "BUY", "confidence": 0.8},
        "research_score": 62,
    })
    after = snapshot({
        "price": 105,
        "trend": "DOWN",
        "momentum": "NEGATIVE",
        "volatility_percent": 4,
        "support": 98,
        "market_regime": "STRONG_TREND_DOWN",
        "technical_structure": "BEARISH",
        "fundamental": {"news_count": 3, "event_count": 1},
        "signal": {"status": "SELL", "confidence": 0.6},
        "research_score": 41,
    })
    result = compare(after, before, "previous_session")
    categories = {item.category for item in result.changes}
    assert {"REGIME", "STRUCTURE", "MOMENTUM", "VOLATILITY", "EVENT", "SIGNAL", "PRICE", "RESEARCH"} <= categories


def test_compare_without_baseline_is_explicit():
    current = snapshot({"market_regime": "RANGE"})
    result = compare(current, None, "previous_week")
    assert result.baseline is None
    assert "No earlier snapshot" in result.summary


def test_previous_day_does_not_use_unrelated_old_snapshot():
    current = snapshot({"market_regime": "RANGE"})
    current.snapshot_at = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    old = ResearchSnapshot(
        id="old",
        symbol="BTC/USD",
        snapshot_type="REPORT",
        snapshot_at=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        state={"market_regime": "STRONG_TREND_DOWN"},
        engine_version="research-intelligence-v1",
    )
    from app.services.research_intelligence import _get_baseline
    assert _get_baseline([current, old], current, "previous_day", None) is None


def test_compare_reports_structured_fundamental_changes():
    before = snapshot({
        "fundamental": {"news_count": 2, "macro_count": 1, "event_count": 1, "headlines": ["old"]},
    })
    after = snapshot({
        "fundamental": {"news_count": 5, "macro_count": 2, "event_count": 3, "headlines": ["new"]},
    })
    result = compare(after, before, "previous_report")
    fields = {item.field for item in result.changes}
    assert {
        "fundamental.news_count",
        "fundamental.macro_count",
        "fundamental.event_count",
        "fundamental.headlines",
    } <= fields


def test_provenance_defaults_model_version():
    from app.models.research_intelligence import ProvenanceRecord
    item = ProvenanceRecord(
        id="p",
        snapshot_id="s",
        claim_type="TEST",
        claim="claim",
        analysis="analysis",
        observed_at=datetime.now(timezone.utc),
        method="test",
        engine_version="research-intelligence-v2",
    )
    assert item.model_version == "deterministic-research"
