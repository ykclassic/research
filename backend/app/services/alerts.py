from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.models.market import Timeframe
from app.services.market_structure import analyze_market_structure
from app.services.quote_service import QuoteService
from app.services.supabase_data import DataNotFoundError, _request
from app.services.technical_analysis import calculate_indicators
from app.symbols import normalize_symbol

ALERT_TYPES = {"RSI_THRESHOLD", "PRICE_CROSS", "REGIME_CHANGE", "BULLISH_BOS"}
CHANNELS = {"WEB", "EMAIL", "DISCORD"}

quote_service = QuoteService()


def list_rules(access_token: str, user_id: str, *, enabled: bool | None = None) -> list[dict[str, Any]]:
    params = {
        "select": "id,user_id,symbol,condition_type,operator,threshold,timeframe,enabled,cooldown_minutes,channels,state,last_triggered_at,created_at,updated_at",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": "100",
    }
    if enabled is not None:
        params["enabled"] = f"eq.{str(enabled).lower()}"
    return _request("GET", "alert_rules", access_token, params=params).json()


def create_rule(access_token: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _validate_rule(payload)
    symbol = normalize_symbol(str(payload["symbol"])).display
    channels = _normalize_channels(payload.get("channels") or ["WEB"])
    response = _request(
        "POST",
        "alert_rules",
        access_token,
        json={
            "user_id": user_id,
            "symbol": symbol,
            "condition_type": payload["condition_type"],
            "operator": payload.get("operator"),
            "threshold": payload.get("threshold"),
            "timeframe": payload.get("timeframe", Timeframe.HOUR_1.value),
            "enabled": payload.get("enabled", True),
            "cooldown_minutes": payload.get("cooldown_minutes", 60),
            "channels": channels,
            "state": {},
        },
        prefer="return=representation",
    )
    rows = response.json()
    if not rows:
        raise RuntimeError("Alert rule was not created.")
    return rows[0]


def update_rule(access_token: str, user_id: str, rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_rule(access_token, user_id, rule_id)
    merged = {**current, **payload}
    _validate_rule(merged)
    update: dict[str, Any] = {}
    for key in ("symbol", "condition_type", "operator", "threshold", "timeframe", "enabled", "cooldown_minutes", "channels"):
        if key in payload:
            update[key] = normalize_symbol(str(payload[key])).display if key == "symbol" else payload[key]
    if "channels" in update:
        update["channels"] = _normalize_channels(update["channels"])
    response = _request(
        "PATCH",
        "alert_rules",
        access_token,
        params={"id": f"eq.{rule_id}", "user_id": f"eq.{user_id}"},
        json=update,
        prefer="return=representation",
    )
    rows = response.json()
    if not rows:
        raise DataNotFoundError("Alert rule was not found.")
    return rows[0]


def get_rule(access_token: str, user_id: str, rule_id: str) -> dict[str, Any]:
    response = _request(
        "GET",
        "alert_rules",
        access_token,
        params={
            "select": "id,user_id,symbol,condition_type,operator,threshold,timeframe,enabled,cooldown_minutes,channels,state,last_triggered_at,created_at,updated_at",
            "id": f"eq.{rule_id}",
            "user_id": f"eq.{user_id}",
        },
    )
    rows = response.json()
    if not rows:
        raise DataNotFoundError("Alert rule was not found.")
    return rows[0]


def delete_rule(access_token: str, user_id: str, rule_id: str) -> None:
    _request("DELETE", "alert_rules", access_token, params={"id": f"eq.{rule_id}", "user_id": f"eq.{user_id}"})


def set_rule_enabled(access_token: str, user_id: str, rule_id: str, enabled: bool) -> dict[str, Any]:
    return update_rule(access_token, user_id, rule_id, {"enabled": enabled})


def list_events(access_token: str, user_id: str, *, unread: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    params = {
        "select": "id,user_id,rule_id,symbol,condition_type,title,message,payload,channels,triggered_at,read_at,created_at",
        "user_id": f"eq.{user_id}",
        "order": "triggered_at.desc",
        "limit": str(max(1, min(limit, 100))),
    }
    if unread:
        params["read_at"] = "is.null"
    return _request("GET", "alert_events", access_token, params=params).json()


def mark_event_read(access_token: str, user_id: str, event_id: str) -> dict[str, Any]:
    response = _request(
        "PATCH",
        "alert_events",
        access_token,
        params={"id": f"eq.{event_id}", "user_id": f"eq.{user_id}"},
        json={"read_at": datetime.now(timezone.utc).isoformat()},
        prefer="return=representation",
    )
    rows = response.json()
    if not rows:
        raise DataNotFoundError("Alert event was not found.")
    return rows[0]


def _validate_rule(payload: dict[str, Any]) -> None:
    condition = payload.get("condition_type")
    if condition not in ALERT_TYPES:
        raise ValueError("Unsupported alert condition.")
    timeframe = payload.get("timeframe", Timeframe.HOUR_1.value)
    try:
        Timeframe(timeframe)
    except ValueError as exc:
        raise ValueError("Unsupported alert timeframe.") from exc
    if condition == "RSI_THRESHOLD":
        if payload.get("operator") not in {"LT", "LTE", "GT", "GTE"}:
            raise ValueError("RSI alerts require LT, LTE, GT, or GTE.")
        threshold = float(payload.get("threshold"))
        if not 0 <= threshold <= 100:
            raise ValueError("RSI threshold must be between 0 and 100.")
    elif condition == "PRICE_CROSS":
        if payload.get("operator") not in {"ABOVE", "BELOW"}:
            raise ValueError("Price-cross alerts require ABOVE or BELOW.")
        if float(payload.get("threshold")) <= 0:
            raise ValueError("Price threshold must be positive.")
    elif payload.get("operator") is not None or payload.get("threshold") is not None:
        raise ValueError("This alert condition does not accept an operator or threshold.")
    cooldown = int(payload.get("cooldown_minutes", 60))
    if cooldown < 0 or cooldown > 10080:
        raise ValueError("Cooldown must be between 0 and 10080 minutes.")


def _normalize_channels(channels: list[str]) -> list[str]:
    normalized = [str(channel).upper() for channel in channels]
    if not normalized or any(channel not in CHANNELS for channel in normalized):
        raise ValueError("Supported alert channels are WEB, EMAIL, and DISCORD.")
    if "WEB" not in normalized:
        normalized.insert(0, "WEB")
    return list(dict.fromkeys(normalized))


def _operator_matches(value: float, operator: str, threshold: float) -> bool:
    return {"LT": value < threshold, "LTE": value <= threshold, "GT": value > threshold, "GTE": value >= threshold}[operator]


def _cooldown_elapsed(rule: dict[str, Any], now: datetime) -> bool:
    last = rule.get("last_triggered_at")
    if not last:
        return True
    previous = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    return (now - previous).total_seconds() >= int(rule.get("cooldown_minutes") or 0) * 60


def _crossed(previous: float | None, current: float, threshold: float, direction: str) -> bool:
    if previous is None:
        return False
    if direction == "ABOVE":
        return previous <= threshold < current
    return previous >= threshold > current


def _latest_bullish_bos(structure) -> Any | None:
    candidates = [event for event in structure.events if event.type == "BOS_BULLISH"]
    return candidates[-1] if candidates else None


async def evaluate_rules(access_token: str, user_id: str) -> list[dict[str, Any]]:
    rules = list_rules(access_token, user_id, enabled=True)
    cache: dict[tuple[str, str], tuple[Any, Any, Any]] = {}
    triggered: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for rule in rules:
        key = (rule["symbol"], rule["timeframe"])
        if key not in cache:
            mapping = normalize_symbol(rule["symbol"])
            timeframe = Timeframe(rule["timeframe"])
            dataset = await asyncio.wait_for(quote_service.orchestrator.get_candles(mapping.internal, timeframe, 250), timeout=20)
            completed = dataset.completed_candles
            if len(completed) < 30:
                continue
            quote = await asyncio.wait_for(quote_service.get_quote(mapping.internal, force_refresh=True), timeout=20)
            indicators = calculate_indicators(list(completed))
            structure = analyze_market_structure(dataset.model_copy(update={"candles": completed}))
            regime = None
            try:
                from app.services.regime_detection import detect_regime
                regime = detect_regime(dataset.model_copy(update={"candles": completed})).regime.value
            except (RuntimeError, ValueError):
                regime = None
            cache[key] = (quote, indicators, (structure, regime, completed[-1].timestamp))

        quote, indicators, (structure, regime, observation_time) = cache[key]
        state = rule.get("state") or {}
        current_price = float(quote.price)
        rsi = indicators.get("rsi14")
        condition = rule["condition_type"]
        active = False
        fingerprint = observation_time.isoformat()
        detail = ""

        if condition == "RSI_THRESHOLD" and rsi is not None:
            threshold = float(rule["threshold"])
            active = _operator_matches(float(rsi), rule["operator"], threshold) and not bool(state.get("condition_active"))
            fingerprint = f"rsi:{observation_time.isoformat()}"
            detail = f"RSI(14) is {float(rsi):.2f} ({rule['operator']} {threshold:g})."
            state["condition_active"] = _operator_matches(float(rsi), rule["operator"], threshold)
        elif condition == "PRICE_CROSS":
            threshold = float(rule["threshold"])
            active = _crossed(state.get("last_price"), current_price, threshold, rule["operator"])
            fingerprint = f"price:{observation_time.isoformat()}"
            detail = f"Price crossed {threshold:,.8g} {'upward' if rule['operator'] == 'ABOVE' else 'downward'} to {current_price:,.8g}."
        elif condition == "REGIME_CHANGE" and regime:
            previous_regime = state.get("last_regime")
            active = previous_regime is not None and previous_regime != regime
            fingerprint = f"regime:{observation_time.isoformat()}"
            detail = f"Regime changed from {previous_regime} to {regime}."
            state["last_regime"] = regime
        elif condition == "BULLISH_BOS":
            bos = _latest_bullish_bos(structure)
            bos_time = bos.time.isoformat() if bos else None
            active = bos_time is not None and bos_time != state.get("last_bos_time")
            fingerprint = f"bos:{bos_time}" if bos_time else f"bos:none:{observation_time.isoformat()}"
            detail = f"Bullish BOS detected at {bos.price:,.8g}." if bos else ""
            if bos_time:
                state["last_bos_time"] = bos_time

        state["last_price"] = current_price
        state["last_observed_at"] = observation_time.isoformat()
        _request("PATCH", "alert_rules", access_token, params={"id": f"eq.{rule['id']}", "user_id": f"eq.{user_id}"}, json={"state": state})

        if not active or not _cooldown_elapsed(rule, now):
            continue
        event_payload = {
            "rule_id": rule["id"],
            "symbol": rule["symbol"],
            "condition_type": condition,
            "timeframe": rule["timeframe"],
            "current_price": current_price,
            "rsi14": rsi,
            "regime": regime,
            "observed_at": observation_time.isoformat(),
        }
        try:
            response = _request(
                "POST",
                "alert_events",
                access_token,
                json={
                    "user_id": user_id,
                    "rule_id": rule["id"],
                    "symbol": rule["symbol"],
                    "condition_type": condition,
                    "title": f"{rule['symbol']} alert",
                    "message": detail,
                    "payload": event_payload,
                    "channels": rule.get("channels") or ["WEB"],
                    "triggered_at": now.isoformat(),
                    "fingerprint": fingerprint,
                },
                prefer="return=representation",
            )
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                continue
            raise
        event_rows = response.json()
        if event_rows:
            _request("PATCH", "alert_rules", access_token, params={"id": f"eq.{rule['id']}", "user_id": f"eq.{user_id}"}, json={"last_triggered_at": now.isoformat()})
            triggered.append(event_rows[0])
    return triggered
