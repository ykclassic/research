from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.market import Timeframe
from app.models.scanner import ScannerConditionRule
from app.config import settings
from app.models.scanner import (
    ScannerConditions,
    ScannerOpportunity,
    ScannerPreset,
    ScannerPresetCreate,
    ScannerRun,
    ScannerSchedule,
    ScannerScheduleCreate,
    ScannerSchedulePatch,
)
from app.preferences.service import preferences_service
from app.services.entitlement import consume_usage, require_feature
from app.services.market_structure import analyze_market_structure
from app.services.regime_detection import detect_regime
from app.services.signal_candle_scheduler import SignalCandleScheduler
from app.services.signal_engine import generate_crypto_signal
from app.services.supabase_data import DataNotFoundError, _request
from app.services.settings_integration import market_data_policy
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol
from app.providers.kraken_public import KrakenPublicProvider
from app.services.scanner_delivery import deliver_scanner_alert

REQUIRED_TIMEFRAMES = (
    Timeframe.DAY_1,
    Timeframe.HOUR_4,
    Timeframe.HOUR_1,
    Timeframe.MINUTE_15,
)
SCAN_TIMEOUT_SECONDS = 20
MAX_SCAN_ASSETS = 50

ALERT_EVENTS = {
    "NEW_QUALIFIED_SIGNAL",
    "SIGNAL_UPGRADE",
    "SIGNAL_DOWNGRADE",
    "REGIME_CHANGE",
    "BOS_CHOCH",
    "LIQUIDITY_SWEEP",
    "SETUP_FORMATION",
    "TARGET_REACHED",
    "INVALIDATION",
    "VOLATILITY_REGIME_CHANGE",
    "RESEARCH_DIVERGENCE",
    "WATCHPOINT",
}

quote_service = QuoteService()
scheduler = SignalCandleScheduler(quote_service, KrakenPublicProvider())


def _parse_preset(row: dict[str, Any]) -> ScannerPreset:
    return ScannerPreset(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        description=row.get("description") or "",
        asset_universe=row.get("asset_universe") or [],
        timeframes=row.get("timeframes") or [item.value for item in REQUIRED_TIMEFRAMES],
        conditions=ScannerConditions.model_validate(row.get("conditions") or {}),
        alert_events=row.get("alert_events") or [],
        enabled=bool(row.get("enabled", True)),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _parse_schedule(row: dict[str, Any]) -> ScannerSchedule:
    return ScannerSchedule(**row)


def list_presets(access_token: str, user_id: str) -> list[ScannerPreset]:
    rows = _request(
        "GET",
        "scanner_presets",
        access_token,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
            "limit": "100",
        },
    ).json()
    return [_parse_preset(row) for row in rows]


def create_preset(access_token: str, user_id: str, payload: ScannerPresetCreate) -> ScannerPreset:
    require_feature(access_token, user_id, "scanner")
    symbols = [normalize_symbol(item).internal for item in payload.asset_universe]
    if len(symbols) > MAX_SCAN_ASSETS:
        raise ValueError(f"A scanner can contain at most {MAX_SCAN_ASSETS} assets.")
    invalid_events = set(payload.alert_events) - ALERT_EVENTS
    if invalid_events:
        raise ValueError(f"Unsupported scanner alert events: {sorted(invalid_events)}")
    row = _request(
        "POST",
        "scanner_presets",
        access_token,
        json={
            "user_id": user_id,
            "name": payload.name.strip(),
            "description": payload.description.strip(),
            "asset_universe": list(dict.fromkeys(symbols)),
            "timeframes": payload.timeframes,
            "conditions": payload.conditions.model_dump(),
            "alert_events": payload.alert_events,
            "enabled": True,
        },
        prefer="return=representation",
    ).json()
    if not row:
        raise RuntimeError("Scanner preset was not created.")
    return _parse_preset(row[0])


def update_preset(access_token: str, user_id: str, preset_id: str, payload: ScannerPresetCreate | ScannerSchedulePatch) -> ScannerPreset:
    current = get_preset(access_token, user_id, preset_id)
    data = payload.model_dump(exclude_none=True)
    if "asset_universe" in data:
        data["asset_universe"] = list(dict.fromkeys(normalize_symbol(item).internal for item in data["asset_universe"]))
        if len(data["asset_universe"]) > MAX_SCAN_ASSETS:
            raise ValueError(f"A scanner can contain at most {MAX_SCAN_ASSETS} assets.")
    if "conditions" in data:
        data["conditions"] = ScannerConditions.model_validate(data["conditions"]).model_dump()
    if "alert_events" in data and set(data["alert_events"]) - ALERT_EVENTS:
        raise ValueError("Unsupported scanner alert event.")
    if not data:
        return current
    row = _request(
        "PATCH",
        "scanner_presets",
        access_token,
        params={"id": f"eq.{preset_id}", "user_id": f"eq.{user_id}"},
        json=data,
        prefer="return=representation",
    ).json()
    if not row:
        raise DataNotFoundError("Scanner preset was not found.")
    return _parse_preset(row[0])


def get_preset(access_token: str, user_id: str, preset_id: str) -> ScannerPreset:
    rows = _request(
        "GET",
        "scanner_presets",
        access_token,
        params={"select": "*", "id": f"eq.{preset_id}", "user_id": f"eq.{user_id}"},
    ).json()
    if not rows:
        raise DataNotFoundError("Scanner preset was not found.")
    return _parse_preset(rows[0])


def delete_preset(access_token: str, user_id: str, preset_id: str) -> None:
    _request(
        "DELETE",
        "scanner_presets",
        access_token,
        params={"id": f"eq.{preset_id}", "user_id": f"eq.{user_id}"},
    )


def _custom_value(signal: Any, volume: float | None, trend: str | None, field: str) -> Any:
    values = {
        "confidence": signal.confidence, "risk_reward": signal.risk_reward,
        "mtf_alignment": signal.mtf_alignment, "momentum": signal.momentum,
        "volatility": signal.volatility, "volume": volume, "direction": signal.signal.value,
        "regime": signal.regime, "structure": signal.market_structure,
        "liquidity": signal.liquidity_conditions, "signal_status": signal.qualification_status.value,
        "trend": trend,
    }
    return values.get(field)


def _rule_matches(value: Any, rule: ScannerConditionRule) -> bool:
    if value is None:
        return False
    target = rule.value
    if rule.operator == "eq": return value == target
    if rule.operator == "neq": return value != target
    if rule.operator == "gt": return float(value) > float(target)
    if rule.operator == "gte": return float(value) >= float(target)
    if rule.operator == "lt": return float(value) < float(target)
    if rule.operator == "lte": return float(value) <= float(target)
    if rule.operator == "contains": return str(target).lower() in str(value).lower()
    if rule.operator == "in": return value in (target if isinstance(target, list) else [target])
    return False


def _matches(signal: Any, volume: float | None, trend: str | None, conditions: ScannerConditions) -> bool:
    if conditions.require_qualified and signal.qualification_status.value != "QUALIFIED":
        return False
    if conditions.min_confidence is not None and signal.confidence < conditions.min_confidence:
        return False
    if conditions.min_risk_reward is not None and (
        signal.risk_reward is None or signal.risk_reward < conditions.min_risk_reward
    ):
        return False
    if conditions.regimes and (signal.regime or "") not in conditions.regimes:
        return False
    if conditions.directions and signal.signal.value not in conditions.directions:
        return False
    if conditions.structures and (signal.market_structure or "") not in conditions.structures:
        return False
    if conditions.min_mtf_alignment is not None and (
        signal.mtf_alignment is None or signal.mtf_alignment < conditions.min_mtf_alignment
    ):
        return False
    if conditions.min_momentum is not None and (
        signal.momentum is None or abs(signal.momentum) < conditions.min_momentum
    ):
        return False
    if conditions.max_volatility is not None and (
        signal.volatility is None or signal.volatility > conditions.max_volatility
    ):
        return False
    if conditions.min_volume is not None and (
        volume is None or volume < conditions.min_volume
    ):
        return False
    if conditions.custom_conditions:
        results = [_rule_matches(_custom_value(signal, volume, trend, rule.field), rule) for rule in conditions.custom_conditions]
        if (conditions.custom_match == "ALL" and not all(results)) or (conditions.custom_match == "ANY" and not any(results)):
            return False
    return True


def _direction(signal: Any) -> str:
    return signal.signal.value


def _historical_evidence(
    access_token: str,
    user_id: str,
    symbol: str,
    timeframe: str,
    regime: str | None,
    structure: str | None,
) -> dict[str, Any]:
    params = {
        "select": "outcome,r_result,confidence",
        "user_id": f"eq.{user_id}",
        "symbol": f"eq.{symbol}",
        "timeframe": f"eq.{timeframe}",
        "limit": "200",
    }
    if regime:
        params["regime"] = f"eq.{regime}"
    if structure:
        params["market_structure"] = f"eq.{structure}"
    rows = _request("GET", "signal_intelligence", access_token, params=params).json()
    resolved = [row for row in rows if row.get("outcome") in {"TARGET_HIT", "STOP_LOSS_HIT"}]
    if not resolved:
        return {"sample_size": 0, "note": "No resolved historical signals match this setup."}
    wins = sum(1 for row in resolved if row["outcome"] == "TARGET_HIT")
    r_values = [float(row["r_result"]) for row in resolved if row.get("r_result") is not None]
    return {
        "sample_size": len(resolved),
        "target_hit_rate": wins / len(resolved),
        "mean_r": sum(r_values) / len(r_values) if r_values else None,
        "sample_sufficient": len(resolved) >= 30,
        "note": "Descriptive historical evidence only; sample is below the minimum threshold." if len(resolved) < 30 else "Descriptive historical evidence from resolved signals.",
    }


async def _scan_symbol(
    access_token: str,
    user_id: str,
    symbol: str,
    conditions: ScannerConditions,
    timeframes: tuple[Timeframe, ...],
    policy: Any,
) -> ScannerOpportunity | None:
    datasets = await asyncio.wait_for(
        scheduler.get_required_datasets(symbol, REQUIRED_TIMEFRAMES, 250, policy),
        timeout=SCAN_TIMEOUT_SECONDS,
    )
    mapping = normalize_symbol(symbol)
    signal = generate_crypto_signal(
        datasets,
        dict(preferences_service.get_or_create(access_token, user_id).signal_preferences),
        selected_timeframes=timeframes,
        asset_class=mapping.asset_class,
    )
    volume = datasets[Timeframe.HOUR_1].completed_candles[-1].volume
    from app.services.technical_analysis import calculate_indicators
    trend = calculate_indicators(list(datasets[Timeframe.HOUR_1].completed_candles)).get("trend")
    if not _matches(signal, volume, trend, conditions):
        return None
    history = _historical_evidence(
        access_token,
        user_id,
        signal.symbol,
        Timeframe.HOUR_1.value,
        signal.regime,
        signal.market_structure,
    )
    setup = signal.strategy
    if signal.market_structure:
        setup = f"{setup} · {signal.market_structure}"
    return ScannerOpportunity(
        symbol=signal.symbol,
        setup=setup,
        regime=signal.regime,
        direction=_direction(signal),
        trend=trend,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        target_price=signal.take_profit,
        last_price=signal.price,
        confidence=signal.confidence,
        risk_reward=signal.risk_reward,
        structure=signal.market_structure,
        liquidity=signal.liquidity_conditions,
        mtf_alignment=signal.mtf_alignment,
        momentum=signal.momentum,
        volatility=signal.volatility,
        volume=float(volume) if volume is not None else None,
        signal_status=signal.qualification_status.value,
        historical_evidence=history,
        signal_id=signal.signal_id,
        observed_at=signal.latest_candle_timestamp,
    )


def _emit_intelligent_events(
    access_token: str,
    user_id: str,
    preset: ScannerPreset,
    opportunity: ScannerOpportunity,
    opportunity_id: str,
) -> None:
    if not preset.alert_events:
        return
    previous_rows = _request(
        "GET",
        "scanner_opportunities",
        access_token,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "symbol": f"eq.{opportunity.symbol}",
            "order": "observed_at.desc",
            "limit": "2",
        },
    ).json()
    previous = next(
        (row for row in previous_rows if row.get("id") != opportunity_id),
        None,
    )
    events: list[tuple[str, str, str]] = []
    if previous is None and "NEW_QUALIFIED_SIGNAL" in preset.alert_events:
        events.append(("NEW_QUALIFIED_SIGNAL", "New qualified signal", f"{opportunity.symbol} produced a qualified {opportunity.direction} setup at {opportunity.confidence:.0%} confidence."))
    if previous:
        previous_confidence = float(previous.get("confidence") or 0)
        if opportunity.confidence - previous_confidence >= 0.05 and "SIGNAL_UPGRADE" in preset.alert_events:
            events.append(("SIGNAL_UPGRADE", "Signal upgraded", f"{opportunity.symbol} confidence increased from {previous_confidence:.0%} to {opportunity.confidence:.0%}."))
        if previous_confidence - opportunity.confidence >= 0.05 and "SIGNAL_DOWNGRADE" in preset.alert_events:
            events.append(("SIGNAL_DOWNGRADE", "Signal downgraded", f"{opportunity.symbol} confidence decreased from {previous_confidence:.0%} to {opportunity.confidence:.0%}."))
        if previous.get("regime") != opportunity.regime and "REGIME_CHANGE" in preset.alert_events:
            events.append(("REGIME_CHANGE", "Regime changed", f"{opportunity.symbol} changed from {previous.get('regime') or 'UNKNOWN'} to {opportunity.regime or 'UNKNOWN'}."))
        if previous.get("structure") != opportunity.structure and "BOS_CHOCH" in preset.alert_events and opportunity.structure:
            events.append(("BOS_CHOCH", "Structure event changed", f"{opportunity.symbol} now reports {opportunity.structure}."))
        if previous.get("setup") != opportunity.setup and "SETUP_FORMATION" in preset.alert_events:
            events.append(("SETUP_FORMATION", "Setup formation", f"{opportunity.symbol} formed {opportunity.setup}."))
        previous_volatility = previous.get("volatility")
        if previous_volatility and opportunity.volatility and (
            opportunity.volatility >= float(previous_volatility) * 1.5
            or opportunity.volatility <= float(previous_volatility) * 0.67
        ) and "VOLATILITY_REGIME_CHANGE" in preset.alert_events:
            events.append(("VOLATILITY_REGIME_CHANGE", "Volatility regime changed", f"{opportunity.symbol} volatility moved from {float(previous_volatility):.4g} to {opportunity.volatility:.4g}."))
    if opportunity.liquidity and "SWEEP" in opportunity.liquidity.upper() and "LIQUIDITY_SWEEP" in preset.alert_events:
        events.append(("LIQUIDITY_SWEEP", "Liquidity sweep detected", f"{opportunity.symbol} reports {opportunity.liquidity}."))
    evidence = opportunity.historical_evidence
    if (
        evidence.get("sample_sufficient")
        and evidence.get("target_hit_rate") is not None
        and abs(float(evidence["target_hit_rate"]) - opportunity.confidence) >= 0.20
        and "RESEARCH_DIVERGENCE" in preset.alert_events
    ):
        events.append(("RESEARCH_DIVERGENCE", "Research divergence", f"{opportunity.symbol} confidence and historical target-hit rate differ materially."))
    if "WATCHPOINT" in preset.alert_events:
        events.append(("WATCHPOINT", "Scanner watchpoint", f"{opportunity.symbol} still satisfies the saved scanner conditions."))
    now = datetime.now(timezone.utc)
    for event_type, title, message in events:
        fingerprint = f"{opportunity.symbol}:{opportunity.observed_at.isoformat()}:{event_type}"
        _request(
            "POST",
            "scanner_alert_events",
            access_token,
            json={
                "user_id": user_id,
                "preset_id": preset.id,
                "opportunity_id": opportunity_id,
                "event_type": event_type,
                "symbol": opportunity.symbol,
                "title": title,
                "message": message,
                "payload": opportunity.model_dump(mode="json"),
                "triggered_at": now.isoformat(),
                "fingerprint": fingerprint,
            },
        )


async def run_scan(
    access_token: str,
    user_id: str,
    preset_id: str,
    *,
    scheduled: bool = False,
) -> ScannerRun:
    if scheduled:
        feature_rows = _request(
            "GET",
            "billing_plan_features",
            access_token,
            params={"select": "plan_id,enabled", "feature_id": "eq.scanner", "enabled": "eq.true"},
        ).json()
        subscriptions = _request(
            "GET",
            "billing_subscriptions",
            access_token,
            params={
                "select": "plan_id,status,trial_ends_at",
                "user_id": f"eq.{user_id}",
                "order": "updated_at.desc",
                "limit": "1",
            },
        ).json()
        plan_id = subscriptions[0]["plan_id"] if subscriptions and subscriptions[0].get("status") in {"trialing", "active", "past_due", "unpaid", "paused"} else "free"
        entitled = any(row["plan_id"] == plan_id for row in feature_rows)
        if not entitled:
            raise PermissionError("Scanner is not entitled for this account.")
    else:
        require_feature(access_token, user_id, "scanner")
        consume_usage(access_token, user_id, "scans")
    preset = get_preset(access_token, user_id, preset_id)
    started = datetime.now(timezone.utc)
    run_rows = _request(
        "POST",
        "scanner_runs",
        access_token,
        json={
            "user_id": user_id,
            "preset_id": preset_id,
            "status": "RUNNING",
            "scanned_count": 0,
            "qualified_count": 0,
            "started_at": started.isoformat(),
        },
        prefer="return=representation",
    ).json()
    if not run_rows:
        raise RuntimeError("Scanner run could not be created.")
    run_id = run_rows[0]["id"]
    record = preferences_service.get_or_create(access_token, user_id)
    policy = market_data_policy(record)
    semaphore = asyncio.Semaphore(2)

    async def one(symbol: str) -> ScannerOpportunity | None:
        async with semaphore:
            try:
                return await _scan_symbol(access_token, user_id, symbol, preset.conditions, policy)
            except (asyncio.TimeoutError, RuntimeError, ValueError):
                return None

    results = await asyncio.gather(*(one(symbol) for symbol in preset.asset_universe))
    opportunities = [item for item in results if item is not None]
    now = datetime.now(timezone.utc)

    for opportunity in opportunities:
        inserted = _request(
            "POST",
            "scanner_opportunities",
            access_token,
            json={
                "run_id": run_id,
                "user_id": user_id,
                **opportunity.model_dump(mode="json"),
                "historical_evidence": opportunity.historical_evidence,
            },
            prefer="return=representation",
        ).json()
        if inserted:
            _emit_intelligent_events(
                access_token,
                user_id,
                preset,
                opportunity,
                inserted[0]["id"],
            )
    _request(
        "PATCH",
        "scanner_runs",
        access_token,
        params={"id": f"eq.{run_id}", "user_id": f"eq.{user_id}"},
        json={
            "status": "COMPLETED",
            "scanned_count": len(preset.asset_universe),
            "qualified_count": len(opportunities),
            "completed_at": now.isoformat(),
        },
    )
    return ScannerRun(
        id=run_id,
        preset_id=preset_id,
        status="COMPLETED",
        scanned_count=len(preset.asset_universe),
        qualified_count=len(opportunities),
        started_at=started,
        completed_at=now,
        opportunities=opportunities,
    )


def latest_opportunities(access_token: str, user_id: str, limit: int = 100) -> list[ScannerOpportunity]:
    rows = _request(
        "GET",
        "scanner_opportunities",
        access_token,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "order": "observed_at.desc",
            "limit": str(min(max(limit, 1), 200)),
        },
    ).json()
    return [ScannerOpportunity(**row) for row in rows]


def list_schedules(access_token: str, user_id: str) -> list[ScannerSchedule]:
    rows = _request(
        "GET",
        "scanner_schedules",
        access_token,
        params={"select": "*", "user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "100"},
    ).json()
    return [_parse_schedule(row) for row in rows]


def create_schedule(access_token: str, user_id: str, payload: ScannerScheduleCreate) -> ScannerSchedule:
    require_feature(access_token, user_id, "scheduled_workflows")
    get_preset(access_token, user_id, payload.preset_id)
    now = datetime.now(timezone.utc)
    row = _request(
        "POST",
        "scanner_schedules",
        access_token,
        json={
            "user_id": user_id,
            "preset_id": payload.preset_id,
            "name": payload.name.strip(),
            "interval_minutes": payload.interval_minutes,
            "enabled": payload.enabled,
            "next_run_at": (now + timedelta(minutes=payload.interval_minutes)).isoformat(),
        },
        prefer="return=representation",
    ).json()
    if not row:
        raise RuntimeError("Scanner schedule was not created.")
    return _parse_schedule(row[0])


def update_schedule(access_token: str, user_id: str, schedule_id: str, payload: ScannerSchedulePatch) -> ScannerSchedule:
    data = payload.model_dump(exclude_none=True)
    row = _request(
        "PATCH",
        "scanner_schedules",
        access_token,
        params={"id": f"eq.{schedule_id}", "user_id": f"eq.{user_id}"},
        json=data,
        prefer="return=representation",
    ).json()
    if not row:
        raise DataNotFoundError("Scanner schedule was not found.")
    return _parse_schedule(row[0])


def delete_schedule(access_token: str, user_id: str, schedule_id: str) -> None:
    _request("DELETE", "scanner_schedules", access_token, params={"id": f"eq.{schedule_id}", "user_id": f"eq.{user_id}"})


def get_due_schedules() -> list[dict[str, Any]]:
    if not settings.supabase_service_role_key:
        return []
    now = datetime.now(timezone.utc)
    return _request(
        "GET",
        "scanner_schedules",
        settings.supabase_service_role_key,
        params={
            "select": "*",
            "enabled": "eq.true",
            "next_run_at": f"lte.{now.isoformat()}",
            "limit": "50",
        },
    ).json()


async def run_due_schedules() -> dict[str, Any]:
    due = get_due_schedules()
    completed = 0
    failed = 0
    for schedule in due:
        try:
            await run_scan(settings.supabase_service_role_key, schedule["user_id"], schedule["preset_id"])
            now = datetime.now(timezone.utc)
            _request(
                "PATCH",
                "scanner_schedules",
                settings.supabase_service_role_key,
                params={"id": f"eq.{schedule['id']}"},
                json={
                    "last_run_at": now.isoformat(),
                    "next_run_at": (now + timedelta(minutes=int(schedule["interval_minutes"]))).isoformat(),
                },
            )
            completed += 1
        except Exception:
            failed += 1
    return {"scheduled": len(due), "completed": completed, "failed": failed}
