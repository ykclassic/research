from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user_or_github_actions
from app.models.market import Timeframe
from app.services.market_session import build_session_state, session_to_dict
from app.services.quote_service import QuoteService

router = APIRouter(
    prefix="/api/market",
    tags=["market"],
    dependencies=[Depends(get_current_user_or_github_actions)],
)

quote_service = QuoteService()

REPRESENTATIVE_SYMBOLS = {
    "crypto": "BTC/USDT",
    "forex": "EURUSD",
    "stocks": "SPY",
}


async def _state(asset_class: str, symbol: str) -> dict[str, object]:
    quote_task = quote_service.get_quote(symbol)
    candle_task = quote_service.orchestrator.get_candles(symbol, Timeframe.HOUR_1, 96)
    quote, dataset = await asyncio.gather(quote_task, candle_task, return_exceptions=True)

    market_open = True
    if isinstance(quote, Exception):
        market_open = asset_class == "crypto"
        quote = None
    else:
        market_open = quote.market_open if quote.market_open is not None else asset_class == "crypto"

    if isinstance(dataset, Exception):
        dataset = None

    state = build_session_state(
        asset_class=asset_class,
        now=datetime.now(timezone.utc),
        market_open=market_open,
        dataset=dataset,
        symbol=symbol,
    )
    return session_to_dict(state)


@router.get("/session")
async def get_market_session() -> dict[str, object]:
    results = await asyncio.gather(
        *(_state(asset_class, symbol) for asset_class, symbol in REPRESENTATIVE_SYMBOLS.items())
    )
    return {
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "sessions": results,
        "representative_symbols": REPRESENTATIVE_SYMBOLS,
    }
