from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.market import Candle, Timeframe
from app.models.signal import CryptoSignal
from app.models.signal_outcome import SignalAuditSnapshot, SignalOutcomeRecord, SignalOutcomeStatus
from app.services.supabase_data import DataConflictError, DataRequestError, _request


SIGNAL_OUTCOME_SELECT = (
    "id,user_id,signal_id,symbol,signal,score,confidence,dispatched_at,entry_price,"
    "stop_loss,target_price,provider,timeframe,signal_engine_version,calculated_at,"
    "latest_candle_timestamp,created_at"
)
OUTCOME_SELECT = (
    "id,signal_id,target_tagged_at,stop_tagged_at,target_tag_latency_seconds,"
    "stop_tag_latency_seconds,first_touch_price,first_touch_timestamp,outcome,"
    "observed_at,observation_candle_timestamp,observation_source,coverage_warning,created_at"
)


def _snapshot_from_row(row: dict[str, Any]) -> SignalAuditSnapshot:
    return SignalAuditSnapshot(
        signal_id=str(row["signal_id"]), symbol=row["symbol"], signal=row["signal"],
        score=float(row["score"]), confidence=float(row["confidence"]),
        dispatched_at=row["dispatched_at"], entry_price=float(row["entry_price"]),
        stop_loss=float(row["stop_loss"]) if row.get("stop_loss") is not None else None,
        target_price=float(row["target_price"]) if row.get("target_price") is not None else None,
        provider=row["provider"], timeframe=row["timeframe"],
        signal_engine_version=row["signal_engine_version"], calculated_at=row["calculated_at"],
        latest_candle_timestamp=row["latest_candle_timestamp"],
    )


def _record(snapshot: SignalAuditSnapshot, outcome: dict[str, Any] | None = None, *, coverage_warning: str | None = None) -> SignalOutcomeRecord:
    outcome = outcome or {}
    return SignalOutcomeRecord(
        **snapshot.model_dump(),
        target_tagged_at=outcome.get("target_tagged_at"),
        stop_tagged_at=outcome.get("stop_tagged_at"),
        target_tag_latency_seconds=outcome.get("target_tag_latency_seconds"),
        stop_tag_latency_seconds=outcome.get("stop_tag_latency_seconds"),
        first_touch_price=outcome.get("first_touch_price"),
        first_touch_timestamp=outcome.get("first_touch_timestamp"),
        outcome=outcome.get("outcome", SignalOutcomeStatus.PENDING),
        observed_at=outcome.get("observed_at"),
        observation_candle_timestamp=outcome.get("observation_candle_timestamp"),
        observation_source=outcome.get("observation_source"),
        coverage_warning=coverage_warning if coverage_warning is not None else outcome.get("coverage_warning"),
    )


def create_signal_audit(access_token: str, user_id: str, signal: CryptoSignal, *, signal_engine_version: str, dispatched_at: datetime | None = None) -> SignalOutcomeRecord:
    signal_id = str(uuid4())
    dispatched = (dispatched_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {
        "user_id": user_id,
        "signal_id": signal_id,
        "symbol": signal.symbol,
        "signal": signal.signal.value,
        "score": signal.score,
        "confidence": signal.confidence,
        "dispatched_at": dispatched.isoformat(),
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "target_price": signal.take_profit,
        "provider": signal.source,
        "timeframe": "15m",
        "signal_engine_version": signal_engine_version,
        "calculated_at": signal.calculated_at.isoformat(),
        "latest_candle_timestamp": signal.latest_candle_timestamp.isoformat(),
    }
    response = _request("POST", "signal_audit_records", access_token, json=payload, prefer="return=representation")
    rows = response.json()
    if not rows:
        raise DataRequestError("Signal audit record was not created.")
    return _record(_snapshot_from_row(rows[0]))


def list_signal_audits(access_token: str, user_id: str, *, limit: int = 50) -> list[SignalOutcomeRecord]:
    response = _request(
        "GET", "signal_audit_records", access_token,
        params={"select": SIGNAL_OUTCOME_SELECT, "user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": str(max(1, min(limit, 100)))},
    )
    rows = response.json()
    if not rows:
        return []
    ids = [str(row["signal_id"]) for row in rows]
    outcomes_response = _request(
        "GET", "signal_audit_outcomes", access_token,
        params={"select": OUTCOME_SELECT, "signal_id": f"in.({','.join(ids)})", "order": "created_at.desc"},
    )
    latest: dict[str, dict[str, Any]] = {}
    for outcome in outcomes_response.json():
        latest.setdefault(str(outcome["signal_id"]), outcome)
    return [_record(_snapshot_from_row(row), latest.get(str(row["signal_id"]))) for row in rows]


def get_signal_audit(access_token: str, user_id: str, signal_id: str) -> SignalOutcomeRecord:
    response = _request("GET", "signal_audit_records", access_token, params={"select": SIGNAL_OUTCOME_SELECT, "signal_id": f"eq.{signal_id}", "user_id": f"eq.{user_id}"})
    rows = response.json()
    if not rows:
        raise DataRequestError("Signal audit record was not found.")
    outcome_response = _request("GET", "signal_audit_outcomes", access_token, params={"select": OUTCOME_SELECT, "signal_id": f"eq.{signal_id}", "order": "created_at.desc", "limit": "1"})
    outcomes = outcome_response.json()
    return _record(_snapshot_from_row(rows[0]), outcomes[0] if outcomes else None)


def append_terminal_outcome(access_token: str, user_id: str, snapshot: SignalAuditSnapshot, result: dict[str, Any]) -> SignalOutcomeRecord:
    payload = {"user_id": user_id, "signal_id": snapshot.signal_id, **result}
    try:
        response = _request("POST", "signal_audit_outcomes", access_token, json=payload, prefer="return=representation")
        rows = response.json()
    except DataConflictError:
        return get_signal_audit(access_token, user_id, snapshot.signal_id)
    if not rows:
        raise DataRequestError("Signal outcome was not recorded.")
    return _record(snapshot, rows[0])


def evaluate_first_touch(snapshot: SignalAuditSnapshot, candles: tuple[Candle, ...]) -> dict[str, Any] | None:
    if snapshot.target_price is None and snapshot.stop_loss is None:
        return None

    direction = snapshot.signal.upper()
    is_buy = direction in {"BUY", "STRONG_BUY"}
    is_sell = direction in {"SELL", "STRONG_SELL"}
    if not (is_buy or is_sell):
        return None

    for candle in candles:
        # The signal was generated from the latest completed candle. A candle
        # whose timestamp is at/before dispatch cannot be a post-dispatch touch.
        if candle.timestamp <= snapshot.dispatched_at or not candle.is_complete:
            continue
        target_hit = snapshot.target_price is not None and (
            candle.high >= snapshot.target_price if is_buy else candle.low <= snapshot.target_price
        )
        stop_hit = snapshot.stop_loss is not None and (
            candle.low <= snapshot.stop_loss if is_buy else candle.high >= snapshot.stop_loss
        )
        if not target_hit and not stop_hit:
            continue

        if target_hit and stop_hit:
            return {
                "outcome": SignalOutcomeStatus.AMBIGUOUS.value,
                "first_touch_price": None,
                "first_touch_timestamp": None,
                "target_tagged_at": None,
                "stop_tagged_at": None,
                "target_tag_latency_seconds": None,
                "stop_tag_latency_seconds": None,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "observation_candle_timestamp": candle.timestamp.isoformat(),
                "observation_source": candle.source,
                "coverage_warning": "Target and stop were both touched in the same completed candle; OHLC data cannot establish intrabar order.",
            }

        touch_price = snapshot.target_price if target_hit else snapshot.stop_loss
        latency = max(0.0, (candle.timestamp - snapshot.dispatched_at).total_seconds())
        if target_hit:
            return {
                "outcome": SignalOutcomeStatus.TARGET_HIT.value,
                "first_touch_price": touch_price,
                "first_touch_timestamp": candle.timestamp.isoformat(),
                "target_tagged_at": candle.timestamp.isoformat(),
                "stop_tagged_at": None,
                "target_tag_latency_seconds": latency,
                "stop_tag_latency_seconds": None,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "observation_candle_timestamp": candle.timestamp.isoformat(),
                "observation_source": candle.source,
            }
        return {
            "outcome": SignalOutcomeStatus.STOP_LOSS_HIT.value,
            "first_touch_price": touch_price,
            "first_touch_timestamp": candle.timestamp.isoformat(),
            "target_tagged_at": None,
            "stop_tagged_at": candle.timestamp.isoformat(),
            "target_tag_latency_seconds": None,
            "stop_tag_latency_seconds": latency,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "observation_candle_timestamp": candle.timestamp.isoformat(),
            "observation_source": candle.source,
        }
    return None
