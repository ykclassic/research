from __future__ import annotations

from datetime import datetime, time, timezone
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
