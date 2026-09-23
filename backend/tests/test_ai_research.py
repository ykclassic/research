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


from app.services.research_copilot import interpret_query


def test_copilot_interprets_comparison_window():
    result = interpret_query("Compare BTC/USD and ETH/USD over the last 30 days.")
    assert result["intent"] == "comparison"
    assert result["days"] == 30
    assert result["assets"] == ["BTC/USD", "ETH/USD"]


def test_copilot_interprets_change_since_yesterday():
    result = interpret_query("What changed since yesterday?")
    assert result["intent"] == "change_analysis"
    assert result["days"] == 2


def test_copilot_interprets_evidence_request():
    assert interpret_query("Show me the evidence behind this conclusion.")["intent"] == "evidence_explanation"


def test_copilot_interprets_historical_setup_request():
    assert interpret_query("Find historical setups similar to this one.")["intent"] == "historical_setup"


def test_copilot_interprets_condition_search():
    assert interpret_query("Which assets currently satisfy these conditions?")["intent"] == "condition_search"
