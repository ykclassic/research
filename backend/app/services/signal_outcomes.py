from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.market import Candle, Timeframe
from app.models.signal import CryptoSignal
from app.models.signal_outcome import SignalOutcomeAuditRecord, SignalOutcomeStatus
from app.services.signal_intelligence import create_intelligence_snapshot, sync_outcome_snapshot
from app.services.supabase_data import (
    DataConflictError,
    DataNotFoundError,
    DataRequestError,
    _request,
)


AUDIT_TIMEFRAME = Timeframe.MINUTE_15
AUDIT_TIMEFRAME_LABEL = AUDIT_TIMEFRAME.value

SELECT_COLUMNS = (
    "id,user_id,signal_id,revision,symbol,signal,score,confidence,"
    "dispatched_at,entry_price,stop_loss,target_price,target_tagged_at,"
    "stop_tagged_at,target_tag_latency_seconds,stop_tag_latency_seconds,"
    "first_touch_price,first_touch_timestamp,outcome,provider,timeframe,"
    "signal_engine_version,calculated_at,latest_candle_timestamp,"
    "created_at,observed_at,observation_candle_timestamp,"
    "observation_source,coverage_warning"
)


def _record(row: dict[str, Any]) -> SignalOutcomeAuditRecord:
    return SignalOutcomeAuditRecord(
        record_id=str(row["id"]),
        signal_id=str(row["signal_id"]),
        revision=int(row["revision"]),
        symbol=row["symbol"],
        signal=row["signal"],
        score=float(row["score"]),
        confidence=float(row["confidence"]),
        dispatched_at=row["dispatched_at"],
        entry_price=float(row["entry_price"]),
        stop_loss=float(row["stop_loss"]) if row.get("stop_loss") is not None else None,
        target_price=float(row["target_price"]) if row.get("target_price") is not None else None,
        target_tagged_at=row.get("target_tagged_at"),
        stop_tagged_at=row.get("stop_tagged_at"),
        target_tag_latency_seconds=(
            float(row["target_tag_latency_seconds"])
            if row.get("target_tag_latency_seconds") is not None
            else None
        ),
        stop_tag_latency_seconds=(
            float(row["stop_tag_latency_seconds"])
            if row.get("stop_tag_latency_seconds") is not None
            else None
        ),
        first_touch_price=(
            float(row["first_touch_price"])
            if row.get("first_touch_price") is not None
            else None
        ),
        first_touch_timestamp=row.get("first_touch_timestamp"),
        outcome=SignalOutcomeStatus(row["outcome"]),
        provider=row["provider"],
        timeframe=row["timeframe"],
        signal_engine_version=row["signal_engine_version"],
        calculated_at=row["calculated_at"],
        latest_candle_timestamp=row["latest_candle_timestamp"],
        observed_at=row["observed_at"],
        observation_candle_timestamp=row.get("observation_candle_timestamp"),
        observation_source=row.get("observation_source"),
        coverage_warning=row.get("coverage_warning"),
    )


def _base_payload(
    user_id: str,
    signal: CryptoSignal,
    *,
    dispatched_at: datetime,
    signal_engine_version: str,
    revision: int,
) -> dict[str, Any]:
    if not signal.research_eligible or signal.qualification_status.value != "QUALIFIED":
        raise ValueError("Only qualified signals can be logged for outcome audit.")
    if signal.signal.value not in {
        "BUY",
        "STRONG_BUY",
        "SELL",
        "STRONG_SELL",
    }:
        raise ValueError("Only directional qualified signals can be logged.")
    if signal.stop_loss is None or signal.take_profit is None:
        raise ValueError("A qualified signal must have both stop loss and target levels.")

    return {
        "user_id": user_id,
        "signal_id": signal.signal_id,
        "revision": revision,
        "symbol": signal.symbol,
        "signal": signal.signal.value,
        "score": signal.score,
        "confidence": signal.confidence,
        "dispatched_at": dispatched_at.astimezone(timezone.utc).isoformat(),
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "target_price": signal.take_profit,
        "target_tagged_at": None,
        "stop_tagged_at": None,
        "target_tag_latency_seconds": None,
        "stop_tag_latency_seconds": None,
        "first_touch_price": None,
        "first_touch_timestamp": None,
        "outcome": SignalOutcomeStatus.PENDING.value,
        "provider": signal.source,
        "timeframe": AUDIT_TIMEFRAME_LABEL,
        "signal_engine_version": signal_engine_version,
        "calculated_at": signal.calculated_at.isoformat(),
        "latest_candle_timestamp": signal.latest_candle_timestamp.isoformat(),
        "observed_at": dispatched_at.astimezone(timezone.utc).isoformat(),
        "observation_candle_timestamp": None,
        "observation_source": None,
        "coverage_warning": None,
    }


def create_signal_audit(
    access_token: str,
    user_id: str,
    signal: CryptoSignal,
    *,
    signal_engine_version: str,
    dispatched_at: datetime | None = None,
) -> SignalOutcomeAuditRecord:
    dispatched = (dispatched_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = _base_payload(
        user_id,
        signal,
        dispatched_at=dispatched,
        signal_engine_version=signal_engine_version,
        revision=1,
    )
    try:
        response = _request(
            "POST",
            "signal_outcome_audit",
            access_token,
            json=payload,
            prefer="return=representation",
        )
    except DataRequestError as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise DataConflictError("This signal has already been logged.") from exc
        raise
    rows = response.json()
    if not rows:
        raise DataRequestError("Signal outcome audit record was not created.")
    record = _record(rows[0])
    create_intelligence_snapshot(access_token, user_id, signal, dispatched_at=dispatched, outcome=record.outcome.value, revision=record.revision)
    return record


def _rows_for_user(
    access_token: str,
    user_id: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    response = _request(
        "GET",
        "signal_outcome_audit",
        access_token,
        params={
            "select": SELECT_COLUMNS,
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
            "limit": str(max(1, min(limit, 250))),
        },
    )
    return response.json()


def list_signal_audits(
    access_token: str,
    user_id: str,
    *,
    limit: int = 50,
) -> list[SignalOutcomeAuditRecord]:
    rows = _rows_for_user(access_token, user_id, limit=min(250, max(limit * 2, limit)))
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest.setdefault(str(row["signal_id"]), row)
    records = [_record(row) for row in latest.values()]
    records.sort(key=lambda item: item.dispatched_at, reverse=True)
    return records[: max(1, min(limit, 100))]


def get_signal_audit(
    access_token: str,
    user_id: str,
    signal_id: str,
) -> SignalOutcomeAuditRecord:
    response = _request(
        "GET",
        "signal_outcome_audit",
        access_token,
        params={
            "select": SELECT_COLUMNS,
            "signal_id": f"eq.{signal_id}",
            "user_id": f"eq.{user_id}",
            "order": "revision.desc",
            "limit": "1",
        },
    )
    rows = response.json()
    if not rows:
        raise DataNotFoundError("Signal outcome audit record was not found.")
    return _record(rows[0])


def _touches(
    snapshot: SignalOutcomeAuditRecord,
    candles: tuple[Candle, ...],
) -> dict[str, Any] | None:
    is_buy = snapshot.signal in {"BUY", "STRONG_BUY"}
    is_sell = snapshot.signal in {"SELL", "STRONG_SELL"}
    if not (is_buy or is_sell):
        return None

    target_timestamp: datetime | None = None
    stop_timestamp: datetime | None = None
    target_price: float | None = None
    stop_price: float | None = None
    target_source: str | None = None
    stop_source: str | None = None

    for candle in candles:
        if not candle.is_complete or candle.timestamp <= snapshot.dispatched_at:
            continue

        target_hit = (
            candle.high >= (snapshot.target_price or float("inf"))
            if is_buy
            else candle.low <= (snapshot.target_price or float("-inf"))
        )
        stop_hit = (
            candle.low <= (snapshot.stop_loss or float("-inf"))
            if is_buy
            else candle.high >= (snapshot.stop_loss or float("inf"))
        )

        if target_hit and target_timestamp is None:
            target_timestamp = candle.timestamp
            target_price = candle.high if is_buy else candle.low
            target_source = candle.source

        if stop_hit and stop_timestamp is None:
            stop_timestamp = candle.timestamp
            stop_price = candle.low if is_buy else candle.high
            stop_source = candle.source

        if target_timestamp is not None and stop_timestamp is not None:
            break

    if target_timestamp is None and stop_timestamp is None:
        return None

    if (
        target_timestamp is not None
        and stop_timestamp is not None
        and target_timestamp == stop_timestamp
    ):
        outcome = SignalOutcomeStatus.AMBIGUOUS
        first_timestamp = None
        first_price = None
        warning = (
            "Target and stop were both touched in the same completed candle; "
            "OHLC data cannot establish intrabar order."
        )
        observation_timestamp = target_timestamp
        observation_source = target_source or stop_source
    elif target_timestamp is not None and (
        stop_timestamp is None or target_timestamp < stop_timestamp
    ):
        outcome = SignalOutcomeStatus.TARGET_HIT
        first_timestamp = target_timestamp
        first_price = target_price
        warning = None
        observation_timestamp = target_timestamp
        observation_source = target_source
    else:
        outcome = SignalOutcomeStatus.STOP_LOSS_HIT
        first_timestamp = stop_timestamp
        first_price = stop_price
        warning = None
        observation_timestamp = stop_timestamp
        observation_source = stop_source

    target_latency = (
        max(0.0, (target_timestamp - snapshot.dispatched_at).total_seconds())
        if target_timestamp is not None
        else None
    )
    stop_latency = (
        max(0.0, (stop_timestamp - snapshot.dispatched_at).total_seconds())
        if stop_timestamp is not None
        else None
    )

    return {
        "target_tagged_at": target_timestamp.isoformat() if target_timestamp else None,
        "stop_tagged_at": stop_timestamp.isoformat() if stop_timestamp else None,
        "target_tag_latency_seconds": target_latency,
        "stop_tag_latency_seconds": stop_latency,
        "first_touch_price": first_price,
        "first_touch_timestamp": (
            first_timestamp.isoformat() if first_timestamp else None
        ),
        "outcome": outcome.value,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "observation_candle_timestamp": (
            observation_timestamp.isoformat() if observation_timestamp else None
        ),
        "observation_source": observation_source,
        "coverage_warning": warning,
    }


def evaluate_first_touch(
    snapshot: SignalOutcomeAuditRecord,
    candles: tuple[Candle, ...],
) -> dict[str, Any] | None:
    return _touches(snapshot, candles)


def append_outcome_snapshot(
    access_token: str,
    user_id: str,
    snapshot: SignalOutcomeAuditRecord,
    result: dict[str, Any],
) -> SignalOutcomeAuditRecord:
    if snapshot.outcome != SignalOutcomeStatus.PENDING:
        return snapshot

    payload = snapshot.model_dump(mode="json")
    payload.pop("record_id", None)
    payload["user_id"] = user_id
    payload["revision"] = snapshot.revision + 1
    payload.update(result)
    payload.pop("created_at", None)

    try:
        response = _request(
            "POST",
            "signal_outcome_audit",
            access_token,
            json=payload,
            prefer="return=representation",
        )
    except DataConflictError:
        # Another refresh may have appended the same revision first.
        return get_signal_audit(access_token, user_id, snapshot.signal_id)

    rows = response.json()
    if not rows:
        raise DataRequestError("Signal outcome snapshot was not recorded.")
    return _record(rows[0])
