from datetime import datetime, timedelta, timezone

from app.models.market import Candle, Timeframe
from app.models.signal_outcome import SignalAuditSnapshot, SignalOutcomeStatus
from app.services.signal_outcomes import evaluate_first_touch


def snapshot(signal: str = "BUY") -> SignalAuditSnapshot:
    dispatched = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    return SignalAuditSnapshot(
        signal_id="00000000-0000-0000-0000-000000000001",
        symbol="BTC/USDT", signal=signal, score=0.8, confidence=0.9,
        dispatched_at=dispatched, entry_price=100, stop_loss=95, target_price=110,
        provider="kraken_public", timeframe="15m", signal_engine_version="1.18.0",
        calculated_at=dispatched - timedelta(seconds=5),
        latest_candle_timestamp=dispatched - timedelta(minutes=15),
    )


def candle(ts: datetime, high: float, low: float) -> Candle:
    return Candle(timestamp=ts, open=100, high=high, low=low, close=100, volume=1, symbol="BTC/USDT", timeframe=Timeframe.MINUTE_15, source="kraken_public", is_complete=True)


def test_target_touch_is_first_official_terminal_outcome():
    result = evaluate_first_touch(snapshot(), (candle(snapshot().dispatched_at + timedelta(minutes=15), 111, 99),))
    assert result is not None
    assert result["outcome"] == SignalOutcomeStatus.TARGET_HIT.value
    assert result["target_tag_latency_seconds"] == 900
    assert result["first_touch_price"] == 110


def test_stop_touch_before_target_is_loss():
    snap = snapshot()
    result = evaluate_first_touch(snap, (candle(snap.dispatched_at + timedelta(minutes=15), 105, 94),))
    assert result is not None
    assert result["outcome"] == SignalOutcomeStatus.STOP_LOSS_HIT.value
    assert result["stop_tag_latency_seconds"] == 900


def test_same_candle_target_and_stop_is_ambiguous_not_hindsight_ordered():
    snap = snapshot()
    result = evaluate_first_touch(snap, (candle(snap.dispatched_at + timedelta(minutes=15), 111, 94),))
    assert result is not None
    assert result["outcome"] == SignalOutcomeStatus.AMBIGUOUS.value
    assert result["first_touch_timestamp"] is None
    assert result["target_tagged_at"] is None
    assert result["stop_tagged_at"] is None


def test_signal_candle_at_or_before_dispatch_is_never_reused():
    snap = snapshot()
    result = evaluate_first_touch(snap, (candle(snap.dispatched_at, 111, 99),))
    assert result is None
