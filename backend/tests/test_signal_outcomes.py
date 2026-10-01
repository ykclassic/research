from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.market import Candle, Timeframe
from app.models.signal_outcome import SignalOutcomeAuditRecord, SignalOutcomeStatus
from app.services.signal_outcomes import evaluate_first_touch


def snapshot(signal: str = "BUY") -> SignalOutcomeAuditRecord:
    dispatched = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    return SignalOutcomeAuditRecord(
        record_id="00000000-0000-0000-0000-000000000001",
        signal_id="00000000-0000-0000-0000-000000000002",
        revision=1,
        symbol="BTC/USDT",
        signal=signal,
        score=0.8,
        confidence=0.9,
        dispatched_at=dispatched,
        entry_price=100,
        stop_loss=105 if signal == "SELL" else 95,
        target_price=90 if signal == "SELL" else 110,
        provider="kraken_public",
        timeframe="15m",
        signal_engine_version="1.18.0",
        calculated_at=dispatched - timedelta(seconds=5),
        latest_candle_timestamp=dispatched - timedelta(minutes=15),
        observed_at=dispatched,
    )


def candle(ts: datetime, high: float, low: float) -> Candle:
    return Candle(
        timestamp=ts,
        open=100,
        high=high,
        low=low,
        close=100,
        volume=1,
        symbol="BTC/USDT",
        timeframe=Timeframe.MINUTE_15,
        source="kraken_public",
        is_complete=True,
    )


def test_buy_target_tag_is_first_official_target_touch():
    snap = snapshot()
    result = evaluate_first_touch(
        snap,
        (
            candle(snap.dispatched_at + timedelta(minutes=15), 109, 99),
            candle(snap.dispatched_at + timedelta(minutes=30), 111, 99),
        ),
    )
    assert result is not None
    assert result["outcome"] == SignalOutcomeStatus.TARGET_HIT.value
    assert result["target_tagged_at"].endswith("12:30:00+00:00")
    assert result["target_tag_latency_seconds"] == 1800
    assert result["first_touch_price"] == 111


def test_sell_target_tag_uses_low():
    snap = snapshot("SELL")
    result = evaluate_first_touch(
        snap,
        (candle(snap.dispatched_at + timedelta(minutes=15), 101, 89),),
    )
    assert result is not None
    assert result["target_tagged_at"].endswith("12:15:00+00:00")
    assert result["outcome"] == SignalOutcomeStatus.TARGET_HIT.value
    assert result["first_touch_price"] == 89


def test_stop_loss_is_recorded_when_it_is_the_first_terminal_touch():
    snap = snapshot()
    result = evaluate_first_touch(
        snap,
        (candle(snap.dispatched_at + timedelta(minutes=15), 105, 94),),
    )
    assert result is not None
    assert result["outcome"] == SignalOutcomeStatus.STOP_LOSS_HIT.value
    assert result["stop_tagged_at"].endswith("12:15:00+00:00")
    assert result["stop_tag_latency_seconds"] == 900
    assert result["first_touch_price"] == 94


def test_same_candle_target_and_stop_is_ambiguous():
    snap = snapshot()
    result = evaluate_first_touch(
        snap,
        (candle(snap.dispatched_at + timedelta(minutes=15), 111, 94),),
    )
    assert result is not None
    assert result["outcome"] == SignalOutcomeStatus.AMBIGUOUS.value
    assert result["target_tagged_at"].endswith("12:15:00+00:00")
    assert result["stop_tagged_at"].endswith("12:15:00+00:00")
    assert result["first_touch_timestamp"] is None


def test_dispatch_candle_is_excluded():
    snap = snapshot()
    assert evaluate_first_touch(
        snap,
        (candle(snap.dispatched_at, 111, 94),),
    ) is None


def test_terminal_cross_outcome_can_append_provenance_repair(monkeypatch):
    from app.services import signal_outcomes

    snap = snapshot()
    snap = snap.model_copy(
        update={
            "provider": "kraken_public_cross",
            "observation_source": "twelve_data",
            "outcome": SignalOutcomeStatus.STOP_LOSS_HIT,
            "stop_tagged_at": snap.dispatched_at + timedelta(minutes=15),
            "stop_tag_latency_seconds": 900,
            "first_touch_price": 94,
            "first_touch_timestamp": snap.dispatched_at + timedelta(minutes=15),
        }
    )

    observed_at = snap.dispatched_at + timedelta(minutes=30)
    result = {
        "target_tagged_at": None,
        "stop_tagged_at": (snap.dispatched_at + timedelta(minutes=15)).isoformat(),
        "target_tag_latency_seconds": None,
        "stop_tag_latency_seconds": 900,
        "first_touch_price": 94,
        "first_touch_timestamp": (
            snap.dispatched_at + timedelta(minutes=15)
        ).isoformat(),
        "outcome": SignalOutcomeStatus.STOP_LOSS_HIT.value,
        "observed_at": observed_at.isoformat(),
        "observation_candle_timestamp": (
            snap.dispatched_at + timedelta(minutes=15)
        ).isoformat(),
        "observation_source": "kraken_public_cross",
        "coverage_warning": None,
    }

    captured: dict[str, object] = {}

    class FakeResponse:
        def json(self):
            row = snap.model_dump(mode="json")
            row["id"] = snap.record_id
            row["user_id"] = "00000000-0000-0000-0000-000000000003"
            row["revision"] = 2
            row.update(result)
            row["created_at"] = observed_at.isoformat()
            return [row]

    def fake_request(method, resource, access_token, **kwargs):
        captured.update(kwargs.get("json", {}))
        return FakeResponse()

    monkeypatch.setattr(signal_outcomes, "_request", fake_request)

    repaired = signal_outcomes.append_outcome_snapshot(
        "token",
        "00000000-0000-0000-0000-000000000003",
        snap,
        result,
    )

    assert repaired.revision == 2
    assert repaired.observation_source == "kraken_public_cross"
    assert captured["revision"] == 2


def test_terminal_native_outcome_without_provenance_mismatch_is_not_reappended(monkeypatch):
    from app.services import signal_outcomes

    snap = snapshot().model_copy(
        update={
            "provider": "kraken_public",
            "observation_source": "kraken_public",
            "outcome": SignalOutcomeStatus.STOP_LOSS_HIT,
        }
    )

    def fail_request(*args, **kwargs):
        raise AssertionError("A correctly sourced terminal outcome must not be reappended.")

    monkeypatch.setattr(signal_outcomes, "_request", fail_request)

    result = {
        "observation_source": "kraken_public",
    }

    assert signal_outcomes.append_outcome_snapshot(
        "token",
        "user",
        snap,
        result,
    ) is snap
\n