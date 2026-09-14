from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.preferences.models import default_preferences
from app.preferences.service import preferences_service
from app.services.research_history import list_history
from app.services.supabase_data import _request, list_watchlists


HISTORY_COLUMNS = [
    "id",
    "record_type",
    "symbol",
    "query",
    "title",
    "saved",
    "created_at",
    "updated_at",
    "payload",
]
WATCHLIST_COLUMNS = ["watchlist_id", "watchlist_name", "symbol", "created_at"]


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        normalized = dict(row)
        if isinstance(normalized.get("payload"), (dict, list)):
            normalized["payload"] = json.dumps(normalized["payload"], ensure_ascii=False, separators=(",", ":"))
        writer.writerow({column: normalized.get(column, "") for column in columns})
    return output.getvalue().encode("utf-8-sig")


def _flatten_watchlists(watchlists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for watchlist in watchlists:
        for item in watchlist.get("watchlist_items") or []:
            rows.append(
                {
                    "watchlist_id": watchlist.get("id"),
                    "watchlist_name": watchlist.get("name"),
                    "symbol": item.get("symbol"),
                    "created_at": item.get("created_at"),
                }
            )
    return rows


def get_history_for_export(access_token: str, user_id: str) -> list[dict[str, Any]]:
    return list_history(access_token, user_id, limit=100)


def get_all_history_for_export(access_token: str, user_id: str) -> list[dict[str, Any]]:
    """Retrieve the user's complete history in bounded pages."""
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = _request(
            "GET",
            "research_history",
            access_token,
            params={
                "select": "id,user_id,record_type,symbol,query,title,payload,saved,created_at,updated_at",
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": "1000",
                "offset": str(offset),
            },
        )
        page = response.json()
        items.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    return items


def history_csv(access_token: str, user_id: str, *, record_type: str | None = None) -> bytes:
    rows = get_all_history_for_export(access_token, user_id)
    if record_type:
        rows = [row for row in rows if row.get("record_type") == record_type]
    return _csv_bytes(rows, HISTORY_COLUMNS)


def watchlists_csv(access_token: str, user_id: str) -> bytes:
    return _csv_bytes(_flatten_watchlists(list_watchlists(access_token, user_id)), WATCHLIST_COLUMNS)


def account_data(access_token: str, user_id: str) -> dict[str, Any]:
    preferences = preferences_service.get_or_create(access_token, user_id)
    watchlists = list_watchlists(access_token, user_id)
    history = get_all_history_for_export(access_token, user_id)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {"user_id": user_id},
        "preferences": {
            "research_preferences": preferences.research_preferences,
            "signal_preferences": preferences.signal_preferences,
            "alert_preferences": preferences.alert_preferences,
            "market_data_preferences": preferences.market_data_preferences,
            "display_preferences": preferences.display_preferences,
            "ai_preferences": preferences.ai_preferences,
            "privacy_preferences": preferences.privacy_preferences,
        },
        "watchlists": watchlists,
        "research_history": history,
    }


def apply_retention(access_token: str, user_id: str, retention_days: int) -> int:
    """Delete expired, non-saved research history and return the deleted count.

    Saved records are intentionally preserved: retention should not silently remove
    research the user explicitly marked as saved. A retention value of zero means
    no automatic deletion (Forever).
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    response = _request(
        "DELETE",
        "research_history",
        access_token,
        params={
            "user_id": f"eq.{user_id}",
            "created_at": f"lt.{cutoff.isoformat()}",
            "saved": "eq.false",
        },
        prefer="return=representation",
    )
    try:
        return len(response.json())
    except ValueError:
        return 0


def privacy_defaults() -> dict[str, Any]:
    return dict(default_preferences()["privacy_preferences"])
