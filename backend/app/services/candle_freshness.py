from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.market import FreshnessStatus, OHLCVDataset
from app.providers.base import freshness_for_age
from app.services.market_sessions import is_market_open
from app.config import settings


def refresh_candle_freshness(
    dataset: OHLCVDataset,
    *,
    now: datetime | None = None,
) -> OHLCVDataset:
    """Recompute candle freshness from the latest *completed* candle.

    Provider timestamps identify the candle's opening time, so freshness must
    be measured from the candle close time rather than from its opening time.
    This also revalidates cached datasets whose stored freshness was calculated
    by an older implementation.
    """
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    latest = dataset.latest_completed_candle
    if latest is None:
        return dataset.model_copy(update={
            "freshness_status": FreshnessStatus.UNKNOWN,
            "freshness_age_seconds": None,
        })

    close_at = latest.timestamp + timedelta(seconds=dataset.timeframe.seconds)
    age = (observed_at - close_at).total_seconds()
    if age < 0:
        return dataset.model_copy(update={
            "freshness_status": FreshnessStatus.UNKNOWN,
            "freshness_age_seconds": 0.0,
        })

    freshness = freshness_for_age(age, settings.stale_quote_seconds)

    # When a traditional exchange is closed, its most recent completed candle
    # remains the current completed market session. Do not manufacture a fresh
    # label, but allow a closed-session dataset to remain semantically usable.
    if freshness == FreshnessStatus.STALE and not is_market_open(dataset.symbol, at=observed_at):
        freshness = FreshnessStatus.DELAYED

    return dataset.model_copy(update={
        "provider_timestamp": latest.timestamp,
        "freshness_status": freshness,
        "freshness_age_seconds": age,
        "completeness_status": dataset.completeness_status,
    })


def require_current_completed_candles(
    dataset: OHLCVDataset,
    *,
    now: datetime | None = None,
) -> OHLCVDataset:
    """Return a dataset suitable for current-state research or raise.

    Historical/stale cache entries are never accepted as current MTF inputs.
    """
    refreshed = refresh_candle_freshness(dataset, now=now)
    if refreshed.latest_completed_candle is None:
        raise ValueError(
            f"{dataset.symbol} {dataset.timeframe.value} has no completed candle."
        )
    if refreshed.freshness_status not in {FreshnessStatus.FRESH, FreshnessStatus.DELAYED}:
        age = refreshed.freshness_age_seconds
        raise ValueError(
            f"{dataset.symbol} {dataset.timeframe.value} candle data is stale "
            f"(latest completed candle age={age:.0f}s); refusing historical data "
            "for current-state research."
        )
    return refreshed
