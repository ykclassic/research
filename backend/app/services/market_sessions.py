from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.symbols import normalize_symbol


NEW_YORK = ZoneInfo("America/New_York")


def is_market_open(symbol: str, *, at: datetime | None = None) -> bool:
    """Return whether the instrument's primary session is open.

    This is deliberately a semantic guard, not a provider-health probe. It is
    used only to distinguish a valid-but-not-current quote from an actual
    provider failure. Exchange holidays are intentionally not inferred here;
    a provider-supplied market-open flag can override this result when one is
    available.
    """
    mapping = normalize_symbol(symbol)
    now = (at or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    weekday = now.weekday()
    current = now.time()

    if mapping.asset_class == "crypto":
        return True

    if mapping.asset_class in {"stock", "etf"}:
        if weekday >= 5:
            return False
        return time(9, 30) <= current < time(16, 0)

    if mapping.asset_class == "forex":
        # FX is conventionally closed from Friday 17:00 ET until Sunday
        # 17:00 ET. The schedule follows New York daylight-saving rules.
        if weekday == 5:
            return False
        if weekday == 6:
            return current >= time(17, 0)
        if weekday == 0 and current < time(17, 0):
            return False
        if weekday == 4 and current >= time(17, 0):
            return False
        return True

    return True



CLOSED_SESSION_CANDLE_AGE_LIMIT_SECONDS = {
    # FX closes Friday 17:00 ET and conventionally reopens Sunday 17:00 ET.
    # The 60-hour cap allows the normal 48-hour closure plus a bounded provider
    # delivery delay. The market-open guard rejects the candle once FX reopens.
    "forex": 60 * 60 * 60,
    # US equity/ETF sessions close Friday 16:00 ET and reopen Monday 09:30 ET.
    # 72 hours bounds the weekend interval plus a modest provider delay.
    "stock": 72 * 60 * 60,
    "etf": 72 * 60 * 60,
}


def closed_session_candle_is_usable(
    symbol: str,
    latest_completed_timestamp: datetime,
    timeframe_seconds: int,
    *,
    at: datetime | None = None,
) -> bool:
    """Whether a completed candle is usable during a bounded market closure.

    This is a historical-research exception only. It does not change quote
    freshness, provider health, or execution eligibility. Unknown asset
    classes and continuously traded crypto never receive this exception.
    """
    mapping = normalize_symbol(symbol)
    maximum_age = CLOSED_SESSION_CANDLE_AGE_LIMIT_SECONDS.get(mapping.asset_class)
    if maximum_age is None:
        return False

    observed_at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if is_market_open(mapping.internal, at=observed_at):
        return False

    if latest_completed_timestamp.tzinfo is None or latest_completed_timestamp.utcoffset() is None:
        return False

    candle_close = latest_completed_timestamp.astimezone(timezone.utc) + timedelta(seconds=timeframe_seconds)
    age_seconds = (observed_at - candle_close).total_seconds()
    return 0 <= age_seconds <= maximum_age
