from datetime import datetime, timezone

from app.models.research_intelligence import ResearchSnapshot, Watchpoint
from app.services.research_intelligence import _evaluate
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


def test_compare_includes_timeframe_specific_state():
    before = snapshot({"timeframes": {"4h": {"support": 100}}, "signal": {"confidence": 0.8}})
    after = snapshot({"timeframes": {"4h": {"support": 92}}, "signal": {"confidence": 0.6}})
    result = compare(after, before, "previous_session")
    fields = {item.field for item in result.changes}
    assert "signal.confidence" in fields


def test_regime_watchpoint_matches_target_without_boolean_string_comparison():
    watchpoint = Watchpoint(
        id="w", symbol="BTC/USD", name="Downtrend", condition_type="REGIME_CHANGE",
        field="market_regime", operator="eq", value="STRONG_TREND_DOWN",
        enabled=True, last_state=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    matched, observed = _evaluate(
        watchpoint,
        snapshot({"market_regime": "STRONG_TREND_DOWN"}),
    )
    assert matched is True
    assert observed == "STRONG_TREND_DOWN"
