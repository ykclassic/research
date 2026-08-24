from datetime import datetime, timezone

from app.models import Quote, QuoteStatus
from app.services.scoring import score_quote


def test_unavailable_quote_cannot_be_scored_as_live():
    quote = Quote(
        symbol="BTC/USD",
        provider_symbol="BTC/USD",
        status=QuoteStatus.UNAVAILABLE,
    )
    result = score_quote(quote)
    assert result["score"] is None
    assert result["confidence"] == 0


def test_live_quote_is_research_eligible():
    quote = Quote(
        symbol="BTC/USD",
        provider_symbol="BTC/USD",
        price=100000,
        timestamp=datetime.now(timezone.utc),
        source="test",
        status=QuoteStatus.LIVE,
    )
    result = score_quote(quote)
    assert result["score"] == 0
