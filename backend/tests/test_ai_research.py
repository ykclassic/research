from app.services.ai_research import AIResearchService


def test_ai_output_text_uses_responses_api_output_text_when_available():
    body = {"model": "gpt-5.6-luna", "output_text": "Verified interpretation."}

    assert AIResearchService._extract_output_text(body) == "Verified interpretation."


def test_ai_output_text_falls_back_to_output_message_parts():
    body = {
        "output": [
            {"type": "reasoning", "content": []},
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Trend is bullish."},
                    {"type": "output_text", "text": "Structure agrees."},
                ],
            },
        ]
    }

    assert AIResearchService._extract_output_text(body) == "Trend is bullish.\n\nStructure agrees."


def test_ai_output_text_rejects_missing_text():
    assert AIResearchService._extract_output_text({"output": []}) == ""
