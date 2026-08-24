from app.models import Quote


def score_quote(quote: Quote) -> dict:
    if quote.price is None or quote.status != "LIVE":
        return {
            "symbol": quote.symbol,
            "score": None,
            "bias": "Unavailable",
            "confidence": 0,
            "reason": "No validated live price is available. Research scoring is disabled.",
        }

    # Placeholder deterministic foundation.
    # Real indicator/structure scoring belongs here after OHLCV ingestion is implemented.
    return {
        "symbol": quote.symbol,
        "score": 0,
        "bias": "Neutral",
        "confidence": 0,
        "reason": "Live price is available; technical scoring requires validated OHLCV history.",
    }
