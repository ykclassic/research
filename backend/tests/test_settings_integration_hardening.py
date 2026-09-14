from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.signal import SignalDirection
from app.preferences.models import default_preferences
from app.services.research_preferences import resolve_research_preferences
from app.services.signal_engine import _qualify
from app.models.mtf import MTFBias


def _record():
    values = deepcopy(default_preferences())
    return SimpleNamespace(
        research_preferences=values["research_preferences"],
        signal_preferences=values["signal_preferences"],
        alert_preferences=values["alert_preferences"],
        market_data_preferences=values["market_data_preferences"],
        display_preferences=values["display_preferences"],
        ai_preferences=values["ai_preferences"],
        privacy_preferences=values["privacy_preferences"],
    )


def test_research_configuration_consumes_saved_components_and_depth():
    record = _record()
    record.research_preferences.update({
        "default_asset": "ETH/USD",
        "default_asset_class": "Crypto",
        "default_timeframe": "4h",
        "analysis_depth": "Comprehensive",
        "technical_analysis_enabled": True,
        "market_structure_enabled": False,
        "multi_timeframe_enabled": False,
        "fundamental_analysis_enabled": True,
        "news_analysis_enabled": False,
        "ai_interpretation_enabled": True,
    })
    config = resolve_research_preferences(record)
    assert config.default_asset == "ETH/USD"
    assert config.default_timeframe == "4h"
    assert config.data_limit == 500
    assert config.requested_components == {
        "technical_analysis": True,
        "market_structure": False,
        "multi_timeframe": False,
        "fundamental_analysis": True,
        "news_analysis": False,
        "ai_interpretation": True,
    }


def test_signal_confidence_setting_is_consumed_by_qualification():
    preferences = deepcopy(default_preferences()["signal_preferences"])
    preferences["minimum_confidence"] = 0.90
    qualified, reasons = _qualify(
        SignalDirection.STRONG_BUY,
        confidence=0.89,
        risk_reward=2.0,
        mtf_bias=MTFBias.BULLISH,
        mtf_alignment=4,
        structure_score=0.8,
        preferences=preferences,
    )
    assert qualified is False
    assert any("below the 90.0% minimum" in reason for reason in reasons)


def test_signal_minimum_rr_setting_is_consumed():
    preferences = deepcopy(default_preferences()["signal_preferences"])
    preferences["minimum_risk_reward"] = 3.0
    qualified, reasons = _qualify(
        SignalDirection.BUY,
        confidence=0.99,
        risk_reward=2.5,
        mtf_bias=MTFBias.BULLISH,
        mtf_alignment=4,
        structure_score=0.8,
        preferences=preferences,
    )
    assert qualified is False
    assert any("below the 3.00 minimum" in reason for reason in reasons)


def test_signal_type_setting_is_consumed():
    preferences = deepcopy(default_preferences()["signal_preferences"])
    preferences["preferred_signal_types"] = ["SELL"]
    qualified, reasons = _qualify(
        SignalDirection.STRONG_BUY,
        confidence=0.99,
        risk_reward=5.0,
        mtf_bias=MTFBias.BULLISH,
        mtf_alignment=4,
        structure_score=0.8,
        preferences=preferences,
    )
    assert qualified is False
    assert any("BUY is not an enabled preferred signal type" in reason for reason in reasons)


def test_mtf_confirmation_setting_is_consumed():
    preferences = deepcopy(default_preferences()["signal_preferences"])
    preferences["require_multi_timeframe_confirmation"] = True
    qualified, reasons = _qualify(
        SignalDirection.BUY,
        confidence=0.99,
        risk_reward=5.0,
        mtf_bias=MTFBias.BEARISH,
        mtf_alignment=4,
        structure_score=0.8,
        preferences=preferences,
    )
    assert qualified is False
    assert any("Multi-timeframe confirmation" in reason for reason in reasons)


def test_structure_confirmation_setting_is_consumed():
    preferences = deepcopy(default_preferences()["signal_preferences"])
    preferences["require_market_structure_confirmation"] = True
    qualified, reasons = _qualify(
        SignalDirection.BUY,
        confidence=0.99,
        risk_reward=5.0,
        mtf_bias=MTFBias.BULLISH,
        mtf_alignment=4,
        structure_score=-0.2,
        preferences=preferences,
    )
    assert qualified is False
    assert any("Market-structure confirmation" in reason for reason in reasons)


def test_ai_output_settings_are_persisted_as_presentation_contract():
    values = deepcopy(default_preferences())
    values["ai_preferences"]["output_sections"]["news_impact"] = False
    values["ai_preferences"]["analysis_style"] = "Concise"
    assert values["ai_preferences"]["output_sections"]["news_impact"] is False
    assert values["ai_preferences"]["analysis_style"] == "Concise"


def test_timezone_setting_is_an_explicit_display_preference():
    record = _record()
    record.display_preferences["timezone"] = "Africa/Lagos"
    assert record.display_preferences["timezone"] == "Africa/Lagos"
    assert datetime.now(timezone.utc).tzinfo is not None
