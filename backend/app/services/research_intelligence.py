from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.news import NewsResearchResponse
from app.preferences.service import preferences_service
from app.services.research_report import ResearchReportService
from app.models.research_intelligence import (
    CatalystRecord,
    ChangeItem,
    ProvenanceRecord,
    ResearchComparison,
    ResearchSnapshot,
    Watchpoint,
    WatchpointEvent,
)
from app.services.news_research_resilient import news_research
from app.services.supabase_data import DataRequestError, _request


ENGINE_VERSION = "research-intelligence-v2"
MODEL_VERSION = "deterministic-research"
SNAPSHOT_SELECT = "id,user_id,symbol,snapshot_type,snapshot_at,source_history_id,state,engine_version,created_at"
WATCHPOINT_SELECT = "id,user_id,symbol,name,condition_type,field,operator,value,timeframe,enabled,last_state,last_triggered_at,created_at,updated_at"
EVENT_SELECT = "id,watchpoint_id,user_id,symbol,event_type,message,observed_value,triggered_at"


def _snapshot(row: dict[str, Any], provenance: tuple[ProvenanceRecord, ...] = ()) -> ResearchSnapshot:
    return ResearchSnapshot(
        id=str(row["id"]),
        symbol=row["symbol"],
        snapshot_type=row["snapshot_type"],
        snapshot_at=row["snapshot_at"],
        source_history_id=row.get("source_history_id"),
        state=row.get("state") or {},
        engine_version=row.get("engine_version") or ENGINE_VERSION,
        provenance=provenance,
    )


def _watchpoint(row: dict[str, Any]) -> Watchpoint:
    return Watchpoint(
        id=str(row["id"]),
        symbol=row["symbol"],
        name=row["name"],
        condition_type=row["condition_type"],
        field=row["field"],
        operator=row["operator"],
        value=row.get("value"),
        timeframe=row.get("timeframe"),
        enabled=bool(row["enabled"]),
        last_state=row.get("last_state"),
        last_triggered_at=row.get("last_triggered_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _event(row: dict[str, Any]) -> WatchpointEvent:
    return WatchpointEvent(
        id=str(row["id"]),
        watchpoint_id=str(row["watchpoint_id"]),
        symbol=row["symbol"],
        event_type=row["event_type"],
        message=row["message"],
        observed_value=row.get("observed_value"),
        triggered_at=row["triggered_at"],
    )


def _provenance(row: dict[str, Any]) -> ProvenanceRecord:
    return ProvenanceRecord(
        id=str(row["id"]),
        snapshot_id=str(row["snapshot_id"]),
        claim_type=row["claim_type"],
        claim=row["claim"],
        analysis=row["analysis"],
        data=row.get("data") or {},
        sources=tuple(row.get("sources") or ()),
        observed_at=row["observed_at"],
        method=row["method"],
        engine_version=row["engine_version"],
        model_version=row.get("model_version") or MODEL_VERSION,
    )


def _latest_signal_state(access_token: str, user_id: str, symbol: str) -> dict[str, Any]:
    try:
        rows = _request("GET", "signal_intelligence", access_token, params={"select": "direction,confidence,outcome,signal_engine_version,dispatched_at", "user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}", "order": "dispatched_at.desc", "limit": "1"}).json()
    except Exception:
        return {}
    if not rows:
        return {}
    row = rows[0]
    return {"status": row.get("direction"), "confidence": float(row["confidence"]) if row.get("confidence") is not None else None, "outcome": row.get("outcome"), "engine_version": row.get("signal_engine_version"), "observed_at": row.get("dispatched_at")}


def _state_from_report(report: Any, signal_state: dict[str, Any] | None = None) -> dict[str, Any]:
    market = report.market_status.model_dump(mode="json")
    regime = report.regime_snapshot or {}
    structure = report.smc_structure.model_dump(mode="json")
    mtf = [item.model_dump(mode="json") for item in report.multi_timeframe]
    timeframes = {str(item.get("timeframe")): item for item in mtf}
    fundamental = report.fundamental_context.model_dump(mode="json")
    signal = signal_state or {
        "status": regime.get("signal") or regime.get("signal_status"),
        "confidence": regime.get("signal_confidence"),
    }
    return {
        "price": market.get("current_price"),
        "change_24h_percent": market.get("change_24h_percent"),
        "trend": market.get("trend"),
        "momentum": market.get("momentum"),
        "volatility_percent": market.get("volatility_percent"),
        "support": market.get("support"),
        "resistance": market.get("resistance"),
        "market_regime": market.get("market_regime"),
        "technical_structure": market.get("technical_structure"),
        "regime_snapshot": regime,
        "structure": structure,
        "multi_timeframe": mtf,
        "timeframes": timeframes,
        "fundamental": fundamental,
        "signal": signal,
        "research_score": report.overall_research_score,
        "score_basis": report.score_basis,
        "invalidation": report.invalidation,
    }


def _sources_from_report(report: Any, signal_state: dict[str, Any] | None = None) -> tuple[str, ...]:
    sources = {"validated market-data providers", "deterministic research engine"}
    if report.fundamental_context.news_count or report.fundamental_context.event_count:
        sources.add("news and event providers")
    if signal_state:
        sources.add("Phase 2 signal intelligence")
    return tuple(sorted(sources))


def _build_provenance(snapshot_id: str, user_id: str, report: Any, observed_at: datetime, signal_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    state = _state_from_report(report, signal_state)
    sources = list(_sources_from_report(report, signal_state))
    common = {
        "snapshot_id": snapshot_id,
        "user_id": user_id,
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "method": "Deterministic ResearchReportService using completed market data and configured research preferences.",
        "engine_version": ENGINE_VERSION,
        "model_version": MODEL_VERSION,
        "sources": sources,
    }
    claims = [
        ("MARKET_STATE", f"{report.symbol} current market state", "Market quote and technical status.", {"market_status": state["price"]}),
        ("REGIME", f"{report.symbol} is in {state['market_regime']}", "Regime detection over the validated candle set.", {"regime": state["market_regime"], "regime_snapshot": state["regime_snapshot"]}),
        ("STRUCTURE", f"{report.symbol} structure is {state['technical_structure']}", "Market-structure analysis over completed candles.", {"structure": state["structure"]}),
        ("MOMENTUM_VOLATILITY", f"{report.symbol} momentum/volatility state", "Technical indicator and volatility calculations.", {"momentum": state["momentum"], "volatility_percent": state["volatility_percent"]}),
        ("FUNDAMENTAL_EVENTS", f"{report.symbol} fundamental and event context", "News and event research when enabled and available.", {"fundamental": state["fundamental"]}),
        ("RESEARCH_SCORE", f"{report.symbol} research score is {report.overall_research_score}/100", "Deterministic composite score; not a probability of profit.", {"score": report.overall_research_score, "score_basis": report.score_basis}),
    ]
    if state["signal"].get("status") is not None or state["signal"].get("confidence") is not None:
        claims.append(("SIGNAL", f"{report.symbol} signal state", "Authoritative Phase 2 signal-intelligence observation when available.", {"signal": state["signal"]}))
    return [{**common, "claim_type": kind, "claim": claim, "analysis": analysis, "data": data} for kind, claim, analysis, data in claims]


def create_snapshot(
    access_token: str,
    user_id: str,
    report: Any,
    *,
    source_history_id: str | None = None,
    snapshot_type: str = "REPORT",
) -> ResearchSnapshot:
    observed_at = report.generated_at.astimezone(timezone.utc)
    signal_state = _latest_signal_state(access_token, user_id, report.symbol)
    state = _state_from_report(report, signal_state)
    payload = {
        "user_id": user_id,
        "symbol": report.symbol,
        "snapshot_type": snapshot_type,
        "snapshot_at": observed_at.isoformat(),
        "source_history_id": source_history_id,
        "state": state,
        "engine_version": ENGINE_VERSION,
    }
    row = _request("POST", "research_snapshots", access_token, json=payload, prefer="return=representation").json()
    if not row:
        raise DataRequestError("Research snapshot was not created.")
    snapshot_id = str(row[0]["id"])
    provenance_rows = _build_provenance(snapshot_id, user_id, report, observed_at, signal_state)
    if provenance_rows:
        _request("POST", "research_provenance", access_token, json=provenance_rows, prefer="return=representation")
    snapshot = _snapshot(row[0])
    return snapshot.model_copy(update={"provenance": _load_provenance(access_token, user_id, snapshot_id)})


def save_snapshot(access_token: str, user_id: str, snapshot_id: str) -> ResearchSnapshot:
    current = get_snapshot(access_token, user_id, snapshot_id)
    payload = {
        "user_id": user_id,
        "symbol": current.symbol,
        "snapshot_type": "SAVED",
        "snapshot_at": current.snapshot_at.isoformat(),
        "source_history_id": current.source_history_id,
        "state": current.state,
        "engine_version": current.engine_version,
    }
    rows = _request("POST", "research_snapshots", access_token, json=payload, prefer="return=representation").json()
    if not rows:
        raise DataRequestError("Saved research snapshot was not created.")
    saved = _snapshot(rows[0])
    provenance_rows = [
        item.model_dump(mode="json", exclude={"id"}) | {"user_id": user_id, "snapshot_id": saved.id}
        for item in current.provenance
    ]
    if provenance_rows:
        _request("POST", "research_provenance", access_token, json=provenance_rows, prefer="return=minimal")
    return saved.model_copy(update={"provenance": current.provenance})


def list_snapshots(access_token: str, user_id: str, symbol: str, limit: int = 100) -> list[ResearchSnapshot]:
    rows = _request(
        "GET", "research_snapshots", access_token,
        params={"select": SNAPSHOT_SELECT, "user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}", "order": "snapshot_at.desc", "limit": str(min(max(limit, 1), 100))}
    ).json()
    return [_snapshot(row) for row in rows]


def _load_provenance(access_token: str, user_id: str, snapshot_id: str) -> tuple[ProvenanceRecord, ...]:
    rows = _request(
        "GET", "research_provenance", access_token,
        params={"select": "id,snapshot_id,claim_type,claim,analysis,data,sources,observed_at,method,engine_version,model_version", "snapshot_id": f"eq.{snapshot_id}", "user_id": f"eq.{user_id}", "order": "observed_at.asc"}
    ).json()
    return tuple(_provenance(row) for row in rows)


def get_snapshot(access_token: str, user_id: str, snapshot_id: str) -> ResearchSnapshot:
    rows = _request("GET", "research_snapshots", access_token, params={"select": SNAPSHOT_SELECT, "id": f"eq.{snapshot_id}", "user_id": f"eq.{user_id}"}).json()
    if not rows:
        raise DataRequestError("Research snapshot was not found.")
    item = _snapshot(rows[0])
    return item.model_copy(update={"provenance": _load_provenance(access_token, user_id, item.id)})


def _get_baseline(snapshots: list[ResearchSnapshot], current: ResearchSnapshot, baseline_type: str, saved_snapshot_id: str | None) -> ResearchSnapshot | None:
    prior = [item for item in snapshots if item.id != current.id and item.snapshot_at < current.snapshot_at]
    if not prior:
        return None
    if baseline_type == "previous_session":
        return next((item for item in prior if item.snapshot_type in {"SESSION", "REPORT"}), prior[0])
    if baseline_type == "previous_report":
        return next((item for item in prior if item.snapshot_type == "REPORT"), None)
    if baseline_type == "previous_day":
        target = current.snapshot_at - timedelta(days=1)
        candidates = [item for item in prior if abs((item.snapshot_at - target).total_seconds()) <= 36 * 3600]
        return min(candidates, key=lambda item: abs((item.snapshot_at - target).total_seconds())) if candidates else None
    if baseline_type == "previous_week":
        target = current.snapshot_at - timedelta(days=7)
        candidates = [item for item in prior if abs((item.snapshot_at - target).total_seconds()) <= 72 * 3600]
        return min(candidates, key=lambda item: abs((item.snapshot_at - target).total_seconds())) if candidates else None
    if baseline_type == "saved":
        if not saved_snapshot_id:
            return next((item for item in prior if item.snapshot_type == "SAVED"), None)
        return next((item for item in snapshots if item.id == saved_snapshot_id), None)
    raise ValueError("Unsupported comparison baseline.")


def _get_path(state: dict[str, Any], path: str) -> Any:
    current: Any = state
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _changed(changes: list[ChangeItem], category: str, field: str, previous: Any, current: Any) -> None:
    if previous == current or (previous is None and current is None):
        return
    significance = "MATERIAL" if category in {"REGIME", "STRUCTURE", "SIGNAL", "EVENT"} else "OBSERVED"
    changes.append(ChangeItem(category=category, field=field, previous=previous, current=current, significance=significance))


def compare(current: ResearchSnapshot, baseline: ResearchSnapshot | None, baseline_type: str) -> ResearchComparison:
    if baseline is None:
        return ResearchComparison(symbol=current.symbol, baseline_type=baseline_type, current=current, baseline=None, summary="No earlier snapshot is available for this comparison.", evidence_note="A change is only reported when two observed snapshots can be compared.")
    a, b = baseline.state, current.state
    changes: list[ChangeItem] = []
    _changed(changes, "REGIME", "market_regime", _get_path(a, "market_regime"), _get_path(b, "market_regime"))
    _changed(changes, "TREND", "trend", _get_path(a, "trend"), _get_path(b, "trend"))
    _changed(changes, "STRUCTURE", "technical_structure", _get_path(a, "technical_structure"), _get_path(b, "technical_structure"))
    _changed(changes, "STRUCTURE", "support", _get_path(a, "support"), _get_path(b, "support"))
    _changed(changes, "STRUCTURE", "resistance", _get_path(a, "resistance"), _get_path(b, "resistance"))
    _changed(changes, "MOMENTUM", "momentum", _get_path(a, "momentum"), _get_path(b, "momentum"))
    _changed(changes, "VOLATILITY", "volatility_percent", _get_path(a, "volatility_percent"), _get_path(b, "volatility_percent"))
    _changed(changes, "EVENT", "fundamental.news_count", _get_path(a, "fundamental.news_count"), _get_path(b, "fundamental.news_count"))
    _changed(changes, "FUNDAMENTAL", "fundamental.macro_count", _get_path(a, "fundamental.macro_count"), _get_path(b, "fundamental.macro_count"))
    _changed(changes, "EVENT", "fundamental.event_count", _get_path(a, "fundamental.event_count"), _get_path(b, "fundamental.event_count"))
    _changed(changes, "FUNDAMENTAL", "fundamental.headlines", _get_path(a, "fundamental.headlines"), _get_path(b, "fundamental.headlines"))
    _changed(changes, "SIGNAL", "signal.status", _get_path(a, "signal.status"), _get_path(b, "signal.status"))
    _changed(changes, "SIGNAL", "signal.confidence", _get_path(a, "signal.confidence"), _get_path(b, "signal.confidence"))
    _changed(changes, "RESEARCH", "research_score", _get_path(a, "research_score"), _get_path(b, "research_score"))
    if _get_path(a, "price") is not None and _get_path(b, "price") is not None:
        _changed(changes, "PRICE", "price", _get_path(a, "price"), _get_path(b, "price"))
    summary = f"{len(changes)} observed change(s) since {baseline.snapshot_at.isoformat()}." if changes else "No tracked state changes were detected."
    return ResearchComparison(symbol=current.symbol, baseline_type=baseline_type, current=current, baseline=baseline, changes=tuple(changes), summary=summary, evidence_note="Changes are descriptive comparisons of stored research snapshots; they are not causal claims.")

def _field_value(snapshot: ResearchSnapshot, field: str) -> Any:
    return _get_path(snapshot.state, field)


def _evaluate(watchpoint: Watchpoint, snapshot: ResearchSnapshot) -> tuple[bool, Any]:
    observed = _field_value(snapshot, watchpoint.field)
    target = watchpoint.value
    if watchpoint.condition_type == "SUPPORT_LOSS":
        price = _field_value(snapshot, "price")
        support = _field_value(snapshot, "support")
        return price is not None and support is not None and price < support, price
    if watchpoint.condition_type == "REGIME_CHANGE":
        return observed == target, observed
    if watchpoint.condition_type == "FIELD_EQUALS":
        return observed == target, observed
    if watchpoint.condition_type == "FIELD_THRESHOLD":
        try:
            left, right = float(observed), float(target)
        except (TypeError, ValueError):
            return False, observed
        return {
            "gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right, "eq": left == right
        }.get(watchpoint.operator, False), observed
    return False, observed


def list_watchpoints(access_token: str, user_id: str, symbol: str | None = None) -> list[Watchpoint]:
    params = {"select": WATCHPOINT_SELECT, "user_id": f"eq.{user_id}", "order": "created_at.desc"}
    if symbol:
        params["symbol"] = f"eq.{symbol}"
    return [_watchpoint(row) for row in _request("GET", "research_watchpoints", access_token, params=params).json()]


def create_watchpoint(access_token: str, user_id: str, payload: dict[str, Any]) -> Watchpoint:
    row = _request("POST", "research_watchpoints", access_token, json={"user_id": user_id, **payload}, prefer="return=representation").json()
    if not row:
        raise DataRequestError("Watchpoint was not created.")
    return _watchpoint(row[0])


def update_watchpoint(access_token: str, user_id: str, watchpoint_id: str, payload: dict[str, Any]) -> Watchpoint:
    row = _request("PATCH", "research_watchpoints", access_token, params={"id": f"eq.{watchpoint_id}", "user_id": f"eq.{user_id}"}, json=payload, prefer="return=representation").json()
    if not row:
        raise DataRequestError("Watchpoint was not found.")
    return _watchpoint(row[0])


def delete_watchpoint(access_token: str, user_id: str, watchpoint_id: str) -> None:
    _request("DELETE", "research_watchpoints", access_token, params={"id": f"eq.{watchpoint_id}", "user_id": f"eq.{user_id}"})


def evaluate_watchpoints(access_token: str, user_id: str, snapshot: ResearchSnapshot) -> list[WatchpointEvent]:
    events: list[WatchpointEvent] = []
    for watchpoint in list_watchpoints(access_token, user_id, snapshot.symbol):
        if not watchpoint.enabled:
            continue
        matched, observed = _evaluate(watchpoint, snapshot)
        should_trigger = matched and watchpoint.last_state is not True
        _request("PATCH", "research_watchpoints", access_token, params={"id": f"eq.{watchpoint.id}", "user_id": f"eq.{user_id}"}, json={"last_state": matched, "last_triggered_at": datetime.now(timezone.utc).isoformat() if should_trigger else watchpoint.last_triggered_at})
        if should_trigger:
            message = f"{watchpoint.name}: {watchpoint.field} {watchpoint.operator} {watchpoint.value!r}; observed {observed!r}."
            row = _request("POST", "research_watchpoint_events", access_token, json={"user_id": user_id, "watchpoint_id": watchpoint.id, "symbol": snapshot.symbol, "event_type": "WATCHPOINT", "message": message, "observed_value": observed, "triggered_at": datetime.now(timezone.utc).isoformat()}, prefer="return=representation").json()
            if row:
                events.append(_event(row[0]))
    return events


def list_watchpoint_events(access_token: str, user_id: str, limit: int = 50) -> list[WatchpointEvent]:
    rows = _request("GET", "research_watchpoint_events", access_token, params={"select": EVENT_SELECT, "user_id": f"eq.{user_id}", "order": "triggered_at.desc", "limit": str(min(max(limit, 1), 100))}).json()
    return [_event(row) for row in rows]


async def catalysts(symbol: str | None, days: int = 7, limit: int = 25) -> tuple[CatalystRecord, ...]:
    research: NewsResearchResponse = await news_research.research(symbol=symbol, days=days, limit=limit)
    records: list[CatalystRecord] = []
    reactions = {item.news_id: item.market_reaction.model_dump(mode="json") for item in research.correlations}
    for item in research.news:
        records.append(CatalystRecord(id=item.id, title=item.headline, event_type=item.event_type.value, source=item.source, source_url=item.source_url, event_timestamp=item.published_at, affected_assets=item.affected_assets, sentiment=item.sentiment.value, market_reaction=reactions.get(item.id, {}), provider=item.provider))
    for event in research.fundamental_events:
        records.append(CatalystRecord(
            id=event.id, title=event.title, event_type=event.event_type.value,
            source=event.source, source_url=event.source_url,
            event_timestamp=event.event_timestamp, affected_assets=event.affected_assets,
            market_reaction={}, provider=event.provider,
        ))
    return tuple(sorted(records, key=lambda item: item.event_timestamp, reverse=True)[:limit])

def _due_snapshot_exists(access_token: str, user_id: str, symbol: str, now: datetime, interval_minutes: int = 15) -> bool:
    rows = _request(
        "GET", "research_snapshots", access_token,
        params={"select": "id,snapshot_at", "user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}", "order": "snapshot_at.desc", "limit": "1"},
    ).json()
    if not rows:
        return False
    last = datetime.fromisoformat(rows[0]["snapshot_at"].replace("Z", "+00:00"))
    return (now - last.astimezone(timezone.utc)).total_seconds() < interval_minutes * 60


async def persist_catalyst_events(access_token: str, user_id: str, symbol: str, days: int = 7) -> int:
    research: NewsResearchResponse = await news_research.research(symbol=symbol, days=days, limit=50)
    reactions = {item.news_id: item.market_reaction.model_dump(mode="json") for item in research.correlations}
    records = []
    for item in research.news:
        records.append({
            "id": item.id, "user_id": user_id, "symbol": symbol, "title": item.headline,
            "event_type": item.event_type.value, "source": item.source, "source_url": item.source_url,
            "event_timestamp": item.published_at.isoformat(), "affected_assets": list(item.affected_assets),
            "sentiment": item.sentiment.value, "market_reaction": reactions.get(item.id, {}),
            "provider": item.provider,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
    for event in research.fundamental_events:
        records.append({
            "id": event.id, "user_id": user_id, "symbol": symbol, "title": event.title,
            "event_type": event.event_type.value, "source": event.source, "source_url": event.source_url,
            "event_timestamp": event.event_timestamp.isoformat(), "affected_assets": list(event.affected_assets),
            "market_reaction": {}, "provider": event.provider,
            "actual": float(event.actual) if isinstance(event.actual, (int, float)) else None,
            "estimate": float(event.estimate) if isinstance(event.estimate, (int, float)) else None,
            "previous": float(event.previous) if isinstance(event.previous, (int, float)) else None,
            "surprise": float(event.surprise) if isinstance(event.surprise, (int, float)) else None,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
    if records:
        _request("POST", "research_catalyst_events", access_token, json=records, prefer="resolution=merge-duplicates,return=minimal")
    return len(records)


async def run_research_intelligence_cycle(access_token: str, interval_minutes: int = 15) -> dict[str, int]:
    """Materialize watched-asset state and evaluate watchpoints on a bounded cadence."""
    now = datetime.now(timezone.utc)
    rows = _request(
        "GET", "research_watchpoints", access_token,
        params={"select": "user_id,symbol", "enabled": "eq.true", "limit": "1000"},
    ).json()
    targets = sorted({(str(row["user_id"]), str(row["symbol"]).upper()) for row in rows})
    service = ResearchReportService()
    snapshots = 0
    events = 0
    failures = 0
    catalysts_persisted = 0
    for user_id, symbol in targets:
        try:
            if _due_snapshot_exists(access_token, user_id, symbol, now, interval_minutes):
                continue
            configuration = None
            try:
                preferences = preferences_service.get_or_create(access_token, user_id)
                from app.services.research_preferences import resolve_research_preferences
                configuration = resolve_research_preferences(preferences)
            except Exception:
                configuration = None
            report = await service.generate(symbol, configuration=configuration)
            snapshot = create_snapshot(access_token, user_id, report, snapshot_type="SESSION")
            events += len(evaluate_watchpoints(access_token, user_id, snapshot))
            try:
                catalysts_persisted += await persist_catalyst_events(access_token, user_id, symbol)
            except Exception:
                pass
            snapshots += 1
        except Exception:
            failures += 1
    return {"targets": len(targets), "snapshots_created": snapshots, "watchpoint_events": events, "catalysts_persisted": catalysts_persisted, "failed_targets": failures}

