from __future__ import annotations

import re
import httpx
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.services.ai_research import AIResearchService
from app.services.research_report import ResearchReportService
from app.services.supabase_data import DataServiceError
from app.services.phase9_infrastructure import queue_event


def _request(method: str, resource: str, access_token: str, *, params: dict[str, str] | None = None, json: Any = None, prefer: str | None = None):
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise ResearchCopilotError("Supabase is not configured.")
    headers = {"apikey": settings.supabase_publishable_key, "Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    response = httpx.request(method, f"{settings.supabase_url.rstrip('/')}/rest/v1/{resource}", headers=headers, params=params, json=json, timeout=settings.provider_timeout_seconds)
    if response.status_code >= 400:
        raise ResearchCopilotError(f"Research data request failed ({response.status_code}).")
    return response

ENGINE_VERSION = "research-copilot-v1"
MODEL_VERSION_FALLBACK = settings.openai_model
SUPPORTED_SYMBOLS = (
    "BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY",
    "NVDA", "AAPL", "MSFT", "SPY",
)


class ResearchCopilotError(RuntimeError):
    pass


def _normalize_symbol(value: str) -> str:
    value = value.strip().upper().replace("-", "/")
    aliases = {"BTC": "BTC/USD", "ETH": "ETH/USD", "SOL": "SOL/USD"}
    return aliases.get(value, value)


def interpret_query(query: str, default_symbol: str = "BTC/USD") -> dict[str, Any]:
    text = query.strip()
    upper = text.upper()
    found = []
    for symbol in SUPPORTED_SYMBOLS:
        if symbol.upper() in upper or symbol.replace("/", "").upper() in upper:
            found.append(symbol)
    symbols = list(dict.fromkeys(found)) or [_normalize_symbol(default_symbol)]

    days = 1
    match = re.search(r"(\d+)\s*days?", text, re.I)
    if match:
        days = max(1, min(365, int(match.group(1))))
    elif re.search(r"last\s+(month|30 days?)", text, re.I):
        days = 30
    elif re.search(r"last\s+week|past\s+week", text, re.I):
        days = 7
    elif re.search(r"since\s+yesterday", text, re.I):
        days = 2

    if re.search(r"compare|versus|\bvs\b|between", text, re.I):
        intent = "comparison"
    elif re.search(r"what changed|since yesterday|deteriorat|improv|changed", text, re.I):
        intent = "change_analysis"
    elif re.search(r"evidence|why|behind this conclusion|support", text, re.I):
        intent = "evidence_explanation"
    elif re.search(r"similar setup|historical setup|historically similar", text, re.I):
        intent = "historical_setup"
    elif re.search(r"which assets|find .*assets|satisfy|conditions", text, re.I):
        intent = "condition_search"
    else:
        intent = "research"

    return {
        "query": text,
        "assets": symbols,
        "days": days,
        "intent": intent,
        "timeframe": "1h",
    }


class ResearchCopilotService:
    def __init__(self) -> None:
        self.report_service = ResearchReportService()
        self.ai_service = AIResearchService()

    @staticmethod
    def _snapshot_rows(access_token: str, user_id: str, symbol: str, days: int) -> list[dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return _request(
            "GET",
            "research_snapshots",
            access_token,
            params={
                "select": "id,symbol,snapshot_type,snapshot_at,state,engine_version,source_history_id",
                "user_id": f"eq.{user_id}",
                "symbol": f"eq.{symbol}",
                "snapshot_at": f"gte.{since}",
                "order": "snapshot_at.asc",
                "limit": "500",
            },
        ).json()

    async def retrieve(self, access_token: str, user_id: str, interpretation: dict[str, Any]) -> dict[str, Any]:
        assets = interpretation["assets"]
        days = interpretation["days"]
        evidence: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        for symbol in assets:
            report = await self.report_service.generate(symbol)
            generated_at = report.generated_at.isoformat()
            evidence.append({
                "id": f"REPORT:{symbol}",
                "claim": f"Deterministic research state for {symbol}.",
                "asset": symbol,
                "type": "deterministic_research_report",
                "timestamp": generated_at,
                "methodology": "ResearchReportService deterministic market-data, feature, regime, structure and multi-timeframe pipeline.",
                "confidence": None,
                "data": report.model_dump(mode="json"),
            })
            snapshots = self._snapshot_rows(access_token, user_id, symbol, days)
            evidence.append({
                "id": f"TIMELINE:{symbol}",
                "claim": f"{len(snapshots)} persisted research snapshots were found for {symbol} in the requested window.",
                "asset": symbol,
                "type": "research_timeline",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "methodology": "Persistent research snapshot history filtered by asset and UTC observation window.",
                "confidence": None,
                "data": snapshots,
            })
            sources.append({
                "asset": symbol,
                "source": "platform deterministic research engine",
                "timestamp": generated_at,
                "methodology": "Validated provider data → deterministic features/regime/structure/MTF → research report.",
            })
        return {
            "retrieval_version": "1.0",
            "intent": interpretation["intent"],
            "assets": assets,
            "timeframe": interpretation["timeframe"],
            "window_days": days,
            "evidence": evidence,
            "sources": sources,
        }

    async def run(
        self,
        access_token: str,
        user_id: str,
        query: str,
        default_symbol: str = "BTC/USD",
    ) -> dict[str, Any]:
        interpretation = interpret_query(query, default_symbol)
        context = await self.retrieve(access_token, user_id, interpretation)
        ai = await self.ai_service.interpret(
            {
                "copilot_query": interpretation,
                "retrieval": context,
                "answer_contract": {
                    "claim": "State the material conclusion only when supported.",
                    "evidence": "Reference evidence IDs exactly as supplied.",
                    "source": "Name the supplied source.",
                    "timestamp": "Use supplied observation timestamps.",
                    "methodology": "Explain the deterministic retrieval method.",
                    "confidence_limitations": "State evidence gaps, sample limitations and uncertainty.",
                },
            },
            query,
        )
        model = ai["model"] or MODEL_VERSION_FALLBACK
        run_row = {
            "user_id": user_id,
            "query": query.strip(),
            "assets": interpretation["assets"],
            "timeframe": interpretation["timeframe"],
            "market_snapshot": {item["id"]: item["data"].get("market_status", {}) for item in context["evidence"] if item["type"] == "deterministic_research_report"},
            "feature_snapshot": {item["id"]: item["data"].get("indicators", {}) for item in context["evidence"] if item["type"] == "deterministic_research_report"},
            "regime_snapshot": {item["id"]: item["data"].get("regime_snapshot", {}) for item in context["evidence"] if item["type"] == "deterministic_research_report"},
            "signal_state": {item["id"]: {"research_score": item["data"].get("overall_research_score"), "score_basis": item["data"].get("score_basis", {})} for item in context["evidence"] if item["type"] == "deterministic_research_report"},
            "evidence": context["evidence"],
            "sources": context["sources"],
            "model": model,
            "model_version": model,
            "engine_version": ENGINE_VERSION,
            "generated_report": ai["report"],
            "metadata": {"intent": interpretation["intent"], "window_days": interpretation["days"], "retrieval_version": context["retrieval_version"]},
        }
        inserted = _request(
            "POST",
            "research_runs",
            access_token,
            json=run_row,
            prefer="return=representation",
        ).json()
        if not inserted:
            raise ResearchCopilotError("Research run could not be persisted.")
        return {
            "run_id": inserted[0]["id"],
            "query": query.strip(),
            "assets": interpretation["assets"],
            "timeframe": interpretation["timeframe"],
            "intent": interpretation["intent"],
            "claim": ai["report"],
            "report": ai["report"],
            "evidence": context["evidence"],
            "sources": context["sources"],
            "methodology": "Natural-language interpretation → deterministic research retrieval → persistent evidence → server-side LLM synthesis.",
            "model": model,
            "model_version": model,
            "engine_version": ENGINE_VERSION,
            "timestamp": inserted[0].get("created_at"),
            "limitations": [
                "AI prose is interpretation; deterministic research data remains authoritative.",
                "Historical similarity is limited to persisted research snapshots unless a dedicated outcome dataset is available.",
            ],
        }

    def history(self, access_token: str, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return _request(
            "GET",
            "research_runs",
            access_token,
            params={
                "select": "id,query,assets,timeframe,model,model_version,engine_version,generated_report,created_at,metadata",
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": str(max(1, min(limit, 100))),
            },
        ).json()


    def list_schedules(self, access_token: str, user_id: str) -> list[dict[str, Any]]:
        return _request(
            "GET", "research_schedules", access_token,
            params={"select": "*", "user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "100"},
        ).json()

    def create_schedule(self, access_token: str, user_id: str, name: str, query: str, interval_minutes: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        row = _request(
            "POST", "research_schedules", access_token,
            json={"user_id": user_id, "name": name.strip(), "query": query.strip(), "interval_minutes": interval_minutes,
                  "next_run_at": (now + timedelta(minutes=interval_minutes)).isoformat()},
            prefer="return=representation",
        ).json()
        if not row:
            raise ResearchCopilotError("Research schedule could not be created.")
        return row[0]

    def delete_schedule(self, access_token: str, user_id: str, schedule_id: str) -> None:
        _request("DELETE", "research_schedules", access_token, params={"id": f"eq.{schedule_id}", "user_id": f"eq.{user_id}"})

    async def run_due_schedules(self, access_token: str) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        due = _request(
            "GET", "research_schedules", access_token,
            params={"select": "*", "enabled": "eq.true", "next_run_at": f"lte.{now.isoformat()}", "limit": "100"},
        ).json()
        completed = 0
        failed = 0
        for schedule in due:
            try:
                await self.run(access_token, schedule["user_id"], schedule["query"])
                next_run = now + timedelta(minutes=int(schedule["interval_minutes"]))
                _request(
                    "PATCH", "research_schedules", access_token,
                    params={"id": f"eq.{schedule['id']}"},
                    json={"last_run_at": now.isoformat(), "next_run_at": next_run.isoformat()},
                )
                completed += 1
            except Exception:
                failed += 1
        return {"scheduled": len(due), "completed": completed, "failed": failed}
