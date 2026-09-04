from __future__ import annotations

from typing import Any

from app.models.market import OHLCVDataset, Timeframe
from app.services.candle_freshness import require_current_completed_candles
from app.services.supabase_data import DataConfigurationError, _request


TABLE = "mtf_candle_cache"


def load_dataset(access_token: str, user_id: str, symbol: str, timeframe: Timeframe) -> OHLCVDataset | None:
    try:
        rows: list[dict[str, Any]] = _request(
            "GET",
            TABLE,
            access_token,
            params={
                "select": "dataset,updated_at",
                "user_id": f"eq.{user_id}",
                "symbol": f"eq.{symbol}",
                "timeframe": f"eq.{timeframe.value}",
                "range_key": "eq.recent",
                "limit": "1",
            },
        ).json()
    except DataConfigurationError:
        return None
    if not rows:
        return None
    raw = rows[0].get("dataset")
    if not isinstance(raw, dict):
        return None
    try:
        dataset = OHLCVDataset.model_validate(raw)
        return require_current_completed_candles(dataset)
    except (ValueError, TypeError):
        return None


def save_dataset(access_token: str, user_id: str, dataset: OHLCVDataset) -> bool:
    try:
        _request(
            "POST",
            TABLE,
            access_token,
            json={
                "user_id": user_id,
                "symbol": dataset.symbol,
                "timeframe": dataset.timeframe.value,
                "range_key": "recent",
                "dataset": dataset.model_dump(mode="json"),
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )
        return True
    except Exception:
        # Persistence is a resilience enhancement, not a reason to reject a
        # validated provider response when the database is temporarily down.
        return False
