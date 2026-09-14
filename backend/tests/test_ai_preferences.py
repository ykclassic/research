from __future__ import annotations

from app.preferences.models import default_preferences
from app.preferences.schemas import AIPreferences
from app.services.ai_research import AIResearchService


def test_s6_defaults_match_required_ai_presentation_controls() -> None:
    preferences = AIPreferences.model_validate(default_preferences()["ai_preferences"])

    assert preferences.enabled is True
    assert preferences.analysis_style == "Analytical"
    assert preferences.interpretation_risk == "Balanced"
    assert preferences.require_evidence is True
    assert preferences.show_confidence_scores is True
    assert preferences.show_supporting_indicators is True
    assert preferences.show_conflicting_evidence is True
    assert all(preferences.output_sections.model_dump().values())


def test_ai_prompt_respects_selected_output_sections_and_style() -> None:
    payload = default_preferences()["ai_preferences"]
    payload["analysis_style"] = "Concise"
    payload["interpretation_risk"] = "Conservative"
    payload["output_sections"] = {
        "executive_summary": True,
        "technical_outlook": True,
        "fundamental_outlook": False,
        "news_impact": False,
        "market_regime": True,
        "bull_scenario": False,
        "base_scenario": True,
        "bear_scenario": False,
        "key_risks": True,
        "catalysts": False,
        "invalidations": True,
    }
    preferences = AIPreferences.model_validate(payload)

    instructions = AIResearchService._presentation_instructions(preferences)

    assert "Analysis style: Concise" in instructions
    assert "Interpretation risk profile: Conservative" in instructions
    assert "Executive summary; Technical outlook; Market regime; Base scenario; Key risks; Invalidations" in instructions
    assert "Fundamental outlook" not in instructions
    assert "Bull scenario" not in instructions


def test_ai_prompt_keeps_integrity_controls_when_evidence_display_is_disabled() -> None:
    payload = default_preferences()["ai_preferences"]
    payload["require_evidence"] = False
    payload["show_confidence_scores"] = False
    payload["show_supporting_indicators"] = False
    payload["show_conflicting_evidence"] = False
    preferences = AIPreferences.model_validate(payload)

    instructions = AIResearchService._presentation_instructions(preferences)

    assert "explicit evidence-ID references are optional" in instructions
    assert "Do not display numeric confidence scores" in instructions
    assert "Do not enumerate supporting indicator values" in instructions
    assert "Do not create a separate conflicting-evidence presentation section" in instructions
    assert "Never invent or estimate" not in instructions
