from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

AssetClass = Literal["Crypto", "Forex", "Stocks"]
Timeframe = Literal["15m", "1h", "4h", "1D"]
AnalysisDepth = Literal["Quick", "Standard", "Comprehensive"]
SignalType = Literal["BUY", "SELL", "NEUTRAL"]
AlertFrequency = Literal["Immediate", "Batched", "Daily digest", "Off"]
Theme = Literal["light", "dark", "system"]
Density = Literal["compact", "comfortable"]
MarketTimestamps = Literal["utc", "local", "exchange"]
AnalysisStyle = Literal["Concise", "Analytical", "Detailed"]
InterpretationRisk = Literal["Conservative", "Balanced", "Aggressive"]
DecimalPrecision = Literal["auto", "0", "2", "4", "6"]
LargeNumberFormat = Literal["compact", "full"]
ChartType = Literal["candlestick", "line", "area"]


class ResearchPreferences(BaseModel):
    default_asset: str = Field(min_length=1, max_length=32)
    default_asset_class: AssetClass
    default_timeframe: Timeframe
    analysis_depth: AnalysisDepth
    technical_analysis_enabled: bool
    market_structure_enabled: bool
    multi_timeframe_enabled: bool
    fundamental_analysis_enabled: bool
    news_analysis_enabled: bool
    ai_interpretation_enabled: bool

    @field_validator("default_asset")
    @classmethod
    def normalize_default_asset(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_default_asset_class(self) -> "ResearchPreferences":
        return self


class SignalPreferences(BaseModel):
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    preferred_signal_types: list[SignalType] = Field(min_length=1, max_length=3)
    minimum_risk_reward: float = Field(ge=0.1, le=20.0)
    require_multi_timeframe_confirmation: bool
    require_market_structure_confirmation: bool

    @field_validator("preferred_signal_types")
    @classmethod
    def unique_signal_types(cls, value: list[SignalType]) -> list[SignalType]:
        if len(set(value)) != len(value):
            raise ValueError("Preferred signal types must be unique.")
        return value


class AlertPreferences(BaseModel):
    browser_notifications_enabled: bool
    email_alerts_enabled: bool
    discord_alerts_enabled: bool
    telegram_alerts_enabled: bool
    high_confidence_signal_alerts: bool
    price_alerts: bool
    regime_change_alerts: bool
    news_event_alerts: bool
    report_completion_alerts: bool
    frequency: AlertFrequency


class MarketDataPreferences(BaseModel):
    maximum_data_age_seconds: Literal[30, 60, 300, 900]
    reject_stale_data: bool
    require_completed_candles: bool
    allow_cached_data_fallback: bool
    crypto_enabled: bool = True
    forex_enabled: bool = True
    stocks_enabled: bool = True


class DisplayPreferences(BaseModel):
    theme: Theme
    density: Density
    sidebar_collapsed: bool
    default_landing_page: Literal["/dashboard", "/markets/watchlists", "/analysis/technical", "/analysis/signals", "/research/ai", "/research/reports"]
    currency: Literal["USD"]
    decimal_precision: DecimalPrecision
    percentage_format: Literal["1.25%", "1.3%", "1%"]
    large_number_format: LargeNumberFormat
    timezone: str = Field(min_length=1, max_length=64)
    market_timestamps: MarketTimestamps
    date_format: Literal["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]
    time_format: Literal["12-hour", "24-hour"]
    chart_type: ChartType
    show_volume: bool
    show_indicators: bool
    show_grid: bool
    remember_zoom: bool
    auto_refresh: bool
    reduce_animations: bool
    reduced_motion: bool
    accessible_contrast: bool

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Timezone must not be empty.")
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone.") from exc
        return normalized


class AIOutputSections(BaseModel):
    executive_summary: bool
    technical_outlook: bool
    fundamental_outlook: bool
    news_impact: bool
    market_regime: bool
    bull_scenario: bool
    base_scenario: bool
    bear_scenario: bool
    key_risks: bool
    catalysts: bool
    invalidations: bool


class AIPreferences(BaseModel):
    enabled: bool
    analysis_style: AnalysisStyle
    interpretation_risk: InterpretationRisk
    require_evidence: bool
    show_confidence_scores: bool
    show_supporting_indicators: bool
    show_conflicting_evidence: bool
    output_sections: AIOutputSections


class PrivacyPreferences(BaseModel):
    research_history_retention_days: Literal[0, 30, 90, 365]
    save_generated_reports: bool
    save_ai_research: bool
    save_search_history: bool
    analytics_telemetry_enabled: bool


class UserPreferences(BaseModel):
    research_preferences: ResearchPreferences
    signal_preferences: SignalPreferences
    alert_preferences: AlertPreferences
    market_data_preferences: MarketDataPreferences
    display_preferences: DisplayPreferences
    ai_preferences: AIPreferences
    privacy_preferences: PrivacyPreferences


class UserPreferencesResponse(UserPreferences):
    id: str
    user_id: str
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    message: str
