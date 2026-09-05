from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings


class AIResearchError(RuntimeError):
    """Raised when the AI interpretation layer cannot produce a report."""


SYSTEM_INSTRUCTIONS = """You are the interpretation layer of a deterministic market-research system.

The supplied Research Context is the only source of market truth. It was calculated by deterministic code from validated provider data before this request reached you.

Hard rules:
- Never invent or estimate prices, timestamps, indicators, candles, market status, statistics, provider facts, or calculated values.
- Never claim to have fetched market data yourself.
- Do not use web search, outside knowledge, memory, or assumptions to fill missing fields.
- If a fact is absent, say that it is not available in the verified context.
- Distinguish deterministic evidence from interpretation.
- Do not convert interpretation into a trading instruction or personalized financial advice.
- Explain conflicting deterministic evidence rather than resolving it by invention.
- Keep the report concise, explicit, and traceable to the supplied evidence IDs.

Return a human-readable research report with these headings:
1. Executive interpretation
2. Trend and regime
3. Market structure
4. Multi-timeframe context
5. Confluence and conflicts
6. Research risks / limitations
7. Evidence references

The Evidence references section must list only evidence IDs that exist in the supplied context.
"""


class AIResearchService:
    def __init__(self) -> None:
        self.endpoint = "https://api.openai.com/v1/responses"

    async def interpret(self, context: dict[str, Any], user_question: str | None = None) -> dict[str, str]:
        if not settings.openai_api_key.strip():
            raise AIResearchError("AI research is not configured. Set OPENAI_API_KEY on the server.")

        payload_context = json.dumps(context, separators=(",", ":"), sort_keys=True, default=str)
        user_input = (
            "Interpret this verified Research Context. Do not add facts that are not present.\n\n"
            f"Research Context:\n{payload_context}"
        )
        if user_question and user_question.strip():
            user_input += f"\n\nUser research question:\n{user_question.strip()}"

        payload = {
            "model": settings.openai_model,
            "store": False,
            "instructions": SYSTEM_INSTRUCTIONS,
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
