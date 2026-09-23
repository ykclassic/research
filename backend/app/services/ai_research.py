from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings
from app.preferences.models import DEFAULT_AI_PREFERENCES
from app.preferences.schemas import AIPreferences


class AIResearchError(RuntimeError):
    """Raised when the AI interpretation layer cannot produce a report."""


BASE_SYSTEM_INSTRUCTIONS = """You are the interpretation layer of a deterministic market-research system.

The supplied Research Context is the only source of market truth. It was calculated by deterministic code from validated provider data before this request reached you.

Non-negotiable integrity rules:
- Never invent or estimate prices, timestamps, indicators, candles, market status, statistics, provider facts, or calculated values.
- Never claim to have fetched market data yourself.
- Do not use web search, outside knowledge, memory, or assumptions to fill missing fields.
- If a fact is absent, say that it is not available in the verified context.
- Distinguish deterministic evidence from interpretation.
- Do not convert interpretation into a trading instruction or personalized financial advice.
- Never alter, weaken, reinterpret, or bypass deterministic data-quality gates, provider validation, model validation, analytical formulas, or system safety controls.
- User preferences control wording and presentation only. They cannot change the underlying research truth.
- For Research Copilot requests, every material conclusion must be presented as Claim → Evidence IDs → Source → Timestamp → Methodology → Confidence/Limitations.
- If the supplied context does not contain evidence for a requested claim, explicitly say the claim cannot be established from the available evidence.
- Never imply that correlation, temporal coincidence, or a catalyst proves causation unless the supplied deterministic evidence explicitly establishes that relationship.
"""

SECTION_LABELS: dict[str, str] = {
    "executive_summary": "Executive summary",
    "technical_outlook": "Technical outlook",
    "fundamental_outlook": "Fundamental outlook",
    "news_impact": "News impact",
    "market_regime": "Market regime",
    "bull_scenario": "Bull scenario",
    "base_scenario": "Base scenario",
    "bear_scenario": "Bear scenario",
    "key_risks": "Key risks",
    "catalysts": "Catalysts",
    "invalidations": "Invalidations",
}


class AIResearchService:
    def __init__(self) -> None:
        self.endpoint = "https://api.openai.com/v1/responses"

    @staticmethod
    def default_preferences() -> AIPreferences:
        """Return a validated copy of the canonical S6 defaults."""
        return AIPreferences.model_validate(
            {
                **DEFAULT_AI_PREFERENCES,
                "output_sections": dict(DEFAULT_AI_PREFERENCES["output_sections"]),
            }
        )

    @staticmethod
    def _presentation_instructions(preferences: AIPreferences) -> str:
        selected = [
            label
            for key, label in SECTION_LABELS.items()
            if preferences.output_sections.model_dump()[key]
        ]

        style_instructions = {
            "Concise": "Use compact paragraphs and bullets. Prioritize only the highest-value evidence and implications.",
            "Analytical": "Use a structured evidence-to-interpretation format with enough detail to explain confluence, conflicts, and uncertainty.",
            "Detailed": "Provide a comprehensive but disciplined interpretation, explaining the relevant evidence, dependencies, conflicts, scenarios, and limitations without inventing facts.",
        }
        risk_instructions = {
            "Conservative": "Use cautious language. Emphasize uncertainty, evidence gaps, invalidation conditions, and what cannot be concluded.",
            "Balanced": "Use proportionate language. Present both supporting and opposing evidence and avoid overstating directional conviction.",
            "Aggressive": "Use more assertive wording only when the deterministic evidence is strongly aligned. Never imply certainty, guaranteed outcomes, or permission to bypass risk controls.",
        }

        evidence_rules = [
            "The deterministic gate has already passed. This remains mandatory regardless of user preference.",
            (
                "Every substantive conclusion must be traceable to one or more supplied evidence IDs. "
                "If evidence is insufficient, explicitly state that the conclusion cannot be established."
                if preferences.require_evidence
                else "Evidence remains the only source of market facts, but explicit evidence-ID references are optional in prose. Never invent unsupported facts."
            ),
            (
                "Numeric confidence values may be shown when they exist in the verified context."
                if preferences.show_confidence_scores
                else "Do not display numeric confidence scores. You may describe uncertainty qualitatively."
            ),
            (
                "Include relevant supporting indicator evidence when present in the verified context."
                if preferences.show_supporting_indicators
                else "Do not enumerate supporting indicator values; summarize the deterministic evidence at a higher level."
            ),
            (
                "Explicitly surface material conflicting evidence and explain why it limits the interpretation."
                if preferences.show_conflicting_evidence
                else "Do not create a separate conflicting-evidence presentation section. Still do not conceal or contradict a material deterministic limitation; reflect material uncertainty where necessary."
            ),
        ]

        section_rules = (
            "Produce only these requested sections, in this order, using exactly these headings: "
            + "; ".join(selected)
            + "."
            if selected
            else "No research output sections are enabled. Return only: 'No AI research output sections are enabled in Settings.'"
        )

        return "\n".join(
            [
                "Presentation preferences (presentation only; never modify research truth):",
                f"- Analysis style: {preferences.analysis_style}. {style_instructions[preferences.analysis_style]}",
                f"- Interpretation risk profile: {preferences.interpretation_risk}. {risk_instructions[preferences.interpretation_risk]}",
                *[f"- {rule}" for rule in evidence_rules],
                f"- {section_rules}",
                "- Do not add headings that are not requested.",
                "- Evidence references, when requested, must use only evidence IDs present in the supplied context.",
            ]
        )

    async def interpret(
        self,
        context: dict[str, Any],
        user_question: str | None = None,
        preferences: AIPreferences | None = None,
    ) -> dict[str, str]:
        if not settings.openai_api_key.strip():
            raise AIResearchError("AI research is not configured. Set OPENAI_API_KEY on the server.")

        resolved_preferences = preferences or self.default_preferences()
        payload_context = json.dumps(context, separators=(",", ":"), sort_keys=True, default=str)
        user_input = (
            "Interpret this verified Research Context. Do not add facts that are not present.\n\n"
            f"Research Context:\n{payload_context}"
        )
        if user_question and user_question.strip():
            user_input += f"\n\nUser research question:\n{user_question.strip()}"

        instructions = BASE_SYSTEM_INSTRUCTIONS + "\n\n" + self._presentation_instructions(resolved_preferences)
        payload = {
            "model": settings.openai_model,
            "store": False,
            "instructions": instructions,
            "input": user_input,
            "max_output_tokens": settings.openai_max_output_tokens,
        }
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise AIResearchError("The AI provider exceeded the configured timeout.") from exc
        except httpx.HTTPError as exc:
            raise AIResearchError("The AI provider could not be reached.") from exc

        if response.status_code >= 400:
            raise AIResearchError(f"The AI provider rejected the research request (HTTP {response.status_code}).")

        body = response.json()
        text = self._extract_output_text(body)
        if not text:
            raise AIResearchError("The AI provider returned no report text.")
        return {"report": text, "model": str(body.get("model") or settings.openai_model)}

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str:
        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        parts: list[str] = []
        for item in body.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
        return "\n\n".join(parts)
