from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.signal import CryptoSignal
from app.models.signal_intelligence import (
    CalibrationBucket,
    SignalCalibration,
    SignalExplorerResult,
    SignalIntelligenceSnapshot,
    SignalReplay,
    SignalReplayCandle,
)
from app.services.entitlement import require_feature, consume_usage
from app.services.supabase_data import DataRequestError, _request

MIN_CALIBRATION_SAMPLE = 30
MIN_SIMILARITY_SAMPLE = 20
SELECT = (
    "id,signal_id,revision,symbol,direction,confidence,dispatched_at,entry_price,"
    "stop_loss,target_price,risk_reward,timeframe,mtf_bias,mtf_alignment,regime,"
    "regime_confidence,market_structure,liquidity_conditions,momentum,volatility,"
    "session,strategy,outcome,target_timestamp,stop_timestamp,first_touch_timestamp,"
    "r_result,outcome_latency_seconds,signal_engine_version,evidence,replay_candles,"
    "structural_conditions"
)


def _row(row: dict[str, Any]) -> SignalIntelligenceSnapshot:
    return SignalIntelligenceSnapshot(
        id=str(row["id"]),
        signal_id=str(row["signal_id"]),
        revision=int(row["revision"]),
        symbol=row["symbol"],
        direction=row["direction"],
        confidence=float(row["confidence"]),
        entry_price=float(row["entry_price"]),
        stop_loss=float(row["stop_loss"]),
        target_price=float(row["target_price"]),
        risk_reward=float(row["risk_reward"]) if row.get("risk_reward") is not None else None,
        timeframe=row["timeframe"],
        mtf_bias=row.get("mtf_bias"),
        mtf_alignment=row.get("mtf_alignment"),
        regime=row.get("regime"),
        regime_confidence=float(row["regime_confidence"]) if row.get("regime_confidence") is not None else None,
        market_structure=row.get("market_structure"),
        liquidity_conditions=row.get("liquidity_conditions"),
        momentum=float(row["momentum"]) if row.get("momentum") is not None else None,
        volatility=float(row["volatility"]) if row.get("volatility") is not None else None,
        session=row.get("session"),
        strategy=row.get("strategy") or "signal_engine",
        outcome=row["outcome"],
        dispatched_at=row["dispatched_at"],
        target_timestamp=row.get("target_timestamp"),
        stop_timestamp=row.get("stop_timestamp"),
        first_touch_timestamp=row.get("first_touch_timestamp"),
        r_result=float(row["r_result"]) if row.get("r_result") is not None else None,
        outcome_latency_seconds=float(row["outcome_latency_seconds"]) if row.get("outcome_latency_seconds") is not None else None,
        signal_engine_version=row["signal_engine_version"],
        evidence=tuple(row.get("evidence") or ()),
        replay_candles=tuple(SignalReplayCandle(**item) for item in (row.get("replay_candles") or ())),
        structural_conditions=row.get("structural_conditions") or {},
    )


def _session_for_signal(signal: CryptoSignal, dispatched_at: datetime) -> str:
    if signal.session:
        return signal.session
    hour = dispatched_at.astimezone(timezone.utc).hour
    if 8 <= hour < 17:
        return "US Activity Window"
    if 2 <= hour < 8:
        return "Europe Activity Window"
    return "Asia Activity Window"


def create_intelligence_snapshot(access_token: str, user_id: str, signal: CryptoSignal, *, dispatched_at: datetime, outcome: str = "PENDING", revision: int = 1, target_timestamp=None, stop_timestamp=None, first_touch_timestamp=None, r_result=None, outcome_latency_seconds=None) -> SignalIntelligenceSnapshot:
    require_feature(access_token, user_id, "signal_intelligence")
    payload = {
        "signal_id": signal.signal_id,
        "revision": revision,
        "user_id": user_id,
        "symbol": signal.symbol,
        "direction": signal.signal.value,
        "confidence": signal.confidence,
        "dispatched_at": dispatched_at.astimezone(timezone.utc).isoformat(),
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "target_price": signal.take_profit,
        "risk_reward": signal.risk_reward,
        "timeframe": "15m",
        "mtf_bias": signal.mtf_bias,
        "mtf_alignment": signal.mtf_alignment,
        "regime": signal.regime,
        "regime_confidence": signal.regime_confidence,
        "market_structure": signal.market_structure,
        "liquidity_conditions": signal.liquidity_conditions,
        "momentum": signal.momentum,
        "volatility": signal.volatility,
        "session": _session_for_signal(signal, dispatched_at),
        "strategy": signal.strategy,
        "outcome": outcome,
        "target_timestamp": target_timestamp.isoformat() if target_timestamp else None,
        "stop_timestamp": stop_timestamp.isoformat() if stop_timestamp else None,
        "first_touch_timestamp": first_touch_timestamp.isoformat() if first_touch_timestamp else None,
        "r_result": r_result,
        "outcome_latency_seconds": outcome_latency_seconds,
        "signal_engine_version": signal.signal_engine_version if hasattr(signal, "signal_engine_version") else "unknown",
        "evidence": list(signal.evidence),
        "replay_candles": [item.model_dump(mode="json") for item in signal.replay_candles],
        "structural_conditions": signal.structural_conditions,
    }
    response = _request("POST", "signal_intelligence", access_token, json=payload, prefer="return=representation")
    rows = response.json()
    if not rows:
        raise DataRequestError("Signal intelligence snapshot was not created.")
    return _row(rows[0])


def _latest_rows(access_token: str, user_id: str, params: dict[str, str]) -> list[SignalIntelligenceSnapshot]:
    base = {"select": SELECT, "user_id": f"eq.{user_id}", "order": "dispatched_at.desc", "limit": "250"}
    base.update(params)
    rows = _request("GET", "signal_intelligence", access_token, params=base).json()
    latest: dict[str, SignalIntelligenceSnapshot] = {}
    for row in rows:
        item = _row(row)
        if item.signal_id not in latest or item.revision > latest[item.signal_id].revision:
            latest[item.signal_id] = item
    return list(latest.values())


def explorer(access_token: str, user_id: str, filters: dict[str, str | None]) -> SignalExplorerResult:
    require_feature(access_token, user_id, "signal_intelligence_analytics")
    consume_usage(access_token, user_id, "historical_queries")
    params: dict[str, str] = {}
    mapping = {
        "symbol": "symbol",
        "timeframe": "timeframe",
        "regime": "regime",
        "strategy": "strategy",
        "session": "session",
        "outcome": "outcome",
        "engine_version": "signal_engine_version",
    }
    for key, column in mapping.items():
        if filters.get(key):
            params[column] = f"eq.{filters[key]}"
    if filters.get("min_confidence"):
        params["confidence"] = f"gte.{filters['min_confidence']}"
    if filters.get("max_confidence"):
        params["confidence"] = f"lte.{filters['max_confidence']}"
    if filters.get("min_rr"):
        params["risk_reward"] = f"gte.{filters['min_rr']}"
    if filters.get("from_date"):
        params["dispatched_at"] = f"gte.{filters['from_date']}T00:00:00+00:00"
    if filters.get("to_date"):
        params["dispatched_at"] = f"lte.{filters['to_date']}T23:59:59+00:00"
    rows = _latest_rows(access_token, user_id, params)
    return SignalExplorerResult(total=len(rows), sample_size_note=("Observed records only; filters do not imply predictive validity." if len(rows) >= MIN_SIMILARITY_SAMPLE else f"Only {len(rows)} observations match. No performance inference should be made until at least {MIN_SIMILARITY_SAMPLE} comparable observations exist."), signals=tuple(rows))


def calibration(access_token: str, user_id: str, filters: dict[str, str | None] | None = None) -> SignalCalibration:
    require_feature(access_token, user_id, "signal_intelligence_analytics")
    consume_usage(access_token, user_id, "historical_queries")
    rows = _latest_rows(access_token, user_id, filters or {})
    buckets = ((0.80, 0.85, "0.80–0.84"), (0.85, 0.90, "0.85–0.89"), (0.90, 0.95, "0.90–0.94"), (0.95, None, "0.95+"))
    result = []
    for lower, upper, label in buckets:
        sample = [item for item in rows if item.confidence >= lower and (upper is None or item.confidence < upper) and item.outcome in {"TARGET_HIT", "STOP_LOSS_HIT"}]
        n = len(sample)
        meaningful = n >= MIN_CALIBRATION_SAMPLE
        wins = sum(item.outcome == "TARGET_HIT" for item in sample)
        observed = wins / n if meaningful else None
        rs = [item.r_result for item in sample if item.r_result is not None]
        result.append(CalibrationBucket(label=label, lower=lower, upper=upper, sample_size=n, observed_outcome_rate=observed, mean_r=(sum(rs) / len(rs) if meaningful and rs else None), statistically_meaningful=meaningful, note=("Observed rate shown because the minimum sample threshold is met." if meaningful else f"Suppressed: {n}/{MIN_CALIBRATION_SAMPLE} resolved outcomes.")))
    return SignalCalibration(minimum_sample_size=MIN_CALIBRATION_SAMPLE, total_samples=sum(item.outcome in {"TARGET_HIT","STOP_LOSS_HIT"} for item in rows), buckets=tuple(result))


def similarity(access_token: str, user_id: str, signal_id: str) -> SignalExplorerResult:
    require_feature(access_token, user_id, "signal_intelligence_analytics")
    consume_usage(access_token, user_id, "historical_queries")
    target_rows = _latest_rows(access_token, user_id, {"signal_id": f"eq.{signal_id}"})
    if not target_rows:
        raise DataRequestError("Signal was not found.")
    target = target_rows[0]
    params = {"symbol": f"eq.{target.symbol}", "timeframe": f"eq.{target.timeframe}", "regime": f"eq.{target.regime}"}
    candidates = [item for item in _latest_rows(access_token, user_id, params) if item.signal_id != target.signal_id]
    def distance(item: SignalIntelligenceSnapshot) -> float:
        confidence = abs(item.confidence - target.confidence) / 0.05
        rr = abs((item.risk_reward or 0) - (target.risk_reward or 0)) / 0.5
        volatility = abs((item.volatility or 0) - (target.volatility or 0)) / max(abs(target.volatility or 1), 1e-9)
        return confidence + rr + volatility
    ranked = sorted(candidates, key=distance)[:100]
    note = ("Similarity set has enough observations for descriptive aggregation." if len(ranked) >= MIN_SIMILARITY_SAMPLE else f"Only {len(ranked)} similar observations found; descriptive statistics are withheld below the {MIN_SIMILARITY_SAMPLE}-observation threshold.")
    return SignalExplorerResult(total=len(ranked), sample_size_note=note, signals=tuple(ranked))


def replay(access_token: str, user_id: str, signal_id: str) -> SignalReplay:
    require_feature(access_token, user_id, "signal_intelligence_analytics")
    consume_usage(access_token, user_id, "historical_queries")
    rows = _latest_rows(access_token, user_id, {"signal_id": f"eq.{signal_id}"})
    if not rows:
        raise DataRequestError("Signal was not found.")
    signal = rows[0]
    states = []
    for candle in sorted(signal.replay_candles, key=lambda item: item.timestamp):
        if candle.timestamp < signal.dispatched_at:
            continue
        states.append({
            "timestamp": candle.timestamp.isoformat(),
            "market_state": "POST_DISPATCH",
            "regime": signal.regime,
            "structure": signal.market_structure,
            "mtf_evidence": {"bias": signal.mtf_bias, "alignment": signal.mtf_alignment},
            "entry": signal.entry_price,
            "stop": signal.stop_loss,
            "target": signal.target_price,
            "candle": candle.model_dump(mode="json"),
        })
    return SignalReplay(signal=signal, chronological_states=tuple(states), outcome=signal.outcome, methodology_note="Replay uses the M15 candles captured with the signal snapshot and preserves their chronological order. OHLC candles cannot establish intrabar order when target and stop occur in the same candle.")


def r_result(entry: float, stop: float, target: float, direction: str, outcome: str) -> float | None:
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if outcome == "TARGET_HIT":
        return abs(target - entry) / risk
    if outcome == "STOP_LOSS_HIT":
        return -1.0
    return None


def sync_outcome_snapshot(access_token: str, user_id: str, outcome_record) -> SignalIntelligenceSnapshot:
    require_feature(access_token, user_id, "signal_intelligence")
    rows = _request("GET", "signal_intelligence", access_token, params={
        "select": SELECT, "user_id": f"eq.{user_id}", "signal_id": f"eq.{outcome_record.signal_id}",
        "order": "revision.desc", "limit": "1",
    }).json()
    if not rows:
        raise DataRequestError("Signal intelligence snapshot is missing.")
    prior = _row(rows[0])
    if prior.outcome == outcome_record.outcome.value and prior.revision >= outcome_record.revision:
        return prior
    target_latency = outcome_record.target_tag_latency_seconds
    stop_latency = outcome_record.stop_tag_latency_seconds
    rvalue = None
    if outcome_record.outcome == "TARGET_HIT":
        rvalue = abs(prior.target_price - prior.entry_price) / abs(prior.entry_price - prior.stop_loss)
    elif outcome_record.outcome == "STOP_LOSS_HIT":
        rvalue = -1.0
    payload = {
        "signal_id": prior.signal_id, "revision": outcome_record.revision, "user_id": user_id,
        "symbol": prior.symbol, "direction": prior.direction, "confidence": prior.confidence,
        "dispatched_at": prior.dispatched_at.isoformat(), "entry_price": prior.entry_price,
        "stop_loss": prior.stop_loss, "target_price": prior.target_price, "risk_reward": prior.risk_reward,
        "timeframe": prior.timeframe, "mtf_bias": prior.mtf_bias, "mtf_alignment": prior.mtf_alignment,
        "regime": prior.regime, "regime_confidence": prior.regime_confidence,
        "market_structure": prior.market_structure, "liquidity_conditions": prior.liquidity_conditions,
        "momentum": prior.momentum, "volatility": prior.volatility, "session": prior.session,
        "strategy": prior.strategy, "outcome": outcome_record.outcome.value,
        "target_timestamp": outcome_record.target_tagged_at.isoformat() if outcome_record.target_tagged_at else None,
        "stop_timestamp": outcome_record.stop_tagged_at.isoformat() if outcome_record.stop_tagged_at else None,
        "first_touch_timestamp": outcome_record.first_touch_timestamp.isoformat() if outcome_record.first_touch_timestamp else None,
        "r_result": rvalue, "outcome_latency_seconds": target_latency or stop_latency,
        "signal_engine_version": prior.signal_engine_version, "evidence": list(prior.evidence),
        "replay_candles": [item.model_dump(mode="json") for item in prior.replay_candles],
        "structural_conditions": prior.structural_conditions,
    }
    response = _request("POST", "signal_intelligence", access_token, json=payload, prefer="return=representation")
    return _row(response.json()[0])
