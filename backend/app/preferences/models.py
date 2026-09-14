from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_RESEARCH_PREFERENCES: dict[str, Any] = {
    "default_asset": "BTC/USD",
    "default_asset_class": "Crypto",
    "default_timeframe": "1h",
    "analysis_depth": "Standard",
    "technical_analysis_enabled": True,
    "market_structure_enabled": True,
    "multi_timeframe_enabled": True,
    "fundamental_analysis_enabled": True,
    "news_analysis_enabled": True,
    "ai_interpretation_enabled": True,
}

DEFAULT_SIGNAL_PREFERENCES: dict[str, Any] = {
    "minimum_confidence": 0.82,
    "preferred_signal_types": ["BUY", "SELL", "NEUTRAL"],
    "minimum_risk_reward": 1.5,
    "require_multi_timeframe_confirmation": False,
    "require_market_structure_confirmation": False,
}

DEFAULT_ALERT_PREFERENCES: dict[str, Any] = {
    "browser_notifications_enabled": False,
    "email_alerts_enabled": False,
    "discord_alerts_enabled": False,
    "telegram_alerts_enabled": False,
    "high_confidence_signal_alerts": True,
    "price_alerts": False,
    "regime_change_alerts": False,
    "news_event_alerts": False,
    "report_completion_alerts": True,
    "frequency": "Immediate",
}

DEFAULT_MARKET_DATA_PREFERENCES: dict[str, Any] = {
    "maximum_data_age_seconds": 300,
    "reject_stale_data": True,
    "require_completed_candles": True,
    "allow_cached_data_fallback": True,
}

DEFAULT_DISPLAY_PREFERENCES: dict[str, Any] = {
    "theme": "system",
    "density": "comfortable",
    "sidebar_collapsed": False,
    "default_landing_page": "/dashboard",
    "currency": "USD",
    "timezone": "Africa/Lagos",
    "market_timestamps": "local",
    "date_format": "DD/MM/YYYY",
    "time_format": "24-hour",
    "reduce_animations": False,
}

DEFAULT_AI_PREFERENCES: dict[str, Any] = {
    "enabled": True,
    "analysis_style": "Analytical",
    "interpretation_risk": "Balanced",
    "require_evidence": True,
    "show_confidence_scores": True,
    "show_supporting_indicators": True,
    "show_conflicting_evidence": True,
    "output_sections": {
        "executive_summary": True,
        "technical_outlook": True,
        "fundamental_outlook": True,
        "news_impact": True,
        "market_regime": True,
        "bull_scenario": True,
        "base_scenario": True,
        "bear_scenario": True,
        "key_risks": True,
        "catalysts": True,
        "invalidations": True,
    },
}

DEFAULT_PRIVACY_PREFERENCES: dict[str, Any] = {
    "research_history_retention_days": 365,
    "save_generated_reports": True,
    "save_ai_research": True,
    "save_search_history": True,
    "analytics_telemetry_enabled": True,
}


@dataclass(frozen=True)
class UserPreferencesRecord:
    id: str
    user_id: str
    research_preferences: dict[str, Any]
    signal_preferences: dict[str, Any]
    alert_preferences: dict[str, Any]
    market_data_preferences: dict[str, Any]
    display_preferences: dict[str, Any]
    ai_preferences: dict[str, Any]
    privacy_preferences: dict[str, Any]
    created_at: str
    updated_at: str


def default_preferences() -> dict[str, Any]:
    return {
        "research_preferences": dict(DEFAULT_RESEARCH_PREFERENCES),
        "signal_preferences": dict(DEFAULT_SIGNAL_PREFERENCES),
        "alert_preferences": dict(DEFAULT_ALERT_PREFERENCES),
        "market_data_preferences": dict(DEFAULT_MARKET_DATA_PREFERENCES),
        "display_preferences": dict(DEFAULT_DISPLAY_PREFERENCES),
        "ai_preferences": {
            **DEFAULT_AI_PREFERENCES,
            "output_sections": dict(DEFAULT_AI_PREFERENCES["output_sections"]),
        },
        "privacy_preferences": dict(DEFAULT_PRIVACY_PREFERENCES),
    }
