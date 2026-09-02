from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, CompletenessStatus, OHLCVDataset, Timeframe
from app.models.market_structure import StructureStatus
from app.services.market_structure import (
    _apply_snapshot_statuses,
    _displacement,
    _equal_levels,
    _event,
    _fvg,
    _inducement,
    _liquidity_and_sweeps,
    _liquidity_extensions,
    _order_blocks,
    _structure_breaks,
    _zone_events,
    analyze_market_structure,
)


def _dataset(prices: list[float], *, source: str = "test") -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i, close in enumerate(prices):
        previous = prices[i - 1] if i else close
        candles.append(Candle(timestamp=start + timedelta(hours=i), open=previous, high=max(close, previous) + 0.8, low=min(close, previous) - 0.8, close=close, volume=1000, symbol="BTC/USDT", timeframe=Timeframe.HOUR_1, source=source, is_complete=True))
    return OHLCVDataset(symbol="BTC/USDT", timeframe=Timeframe.HOUR_1, source=source, requested_at=start, candles=tuple(candles), completeness_status=CompletenessStatus.COMPLETE)


def _ohlc_dataset(candles: list[tuple[float, float, float, float]]) -> OHLCVDataset:
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    rows = tuple(Candle(timestamp=start + timedelta(hours=i), open=o, high=h, low=l, close=c, volume=1000, symbol="BTC/USDT", timeframe=Timeframe.HOUR_1, source="fixture", is_complete=True) for i, (o, h, l, c) in enumerate(candles))
    return OHLCVDataset(symbol="BTC/USDT", timeframe=Timeframe.HOUR_1, source="fixture", requested_at=start, candles=rows, completeness_status=CompletenessStatus.COMPLETE)


def test_market_structure_emits_required_audit_fields() -> None:
    result = analyze_market_structure(_dataset([100, 102, 104, 102, 100, 103, 106, 104, 101, 105, 109, 107] * 4))
    assert result.events
    for event in result.events:
        assert event.type and event.price > 0 and event.time.tzinfo is not None
        assert event.timeframe is Timeframe.HOUR_1 and 0 <= event.strength <= 1
        assert isinstance(event.status, StructureStatus) and event.source_candles
        assert event.time >= event.source_candles[-1]


def test_swing_confirmation_does_not_use_future_candles() -> None:
    prices = [100, 104, 108, 104, 100, 103, 107, 103, 99, 102, 106, 102] * 4
    base = analyze_market_structure(_dataset(prices))
    extended = analyze_market_structure(_dataset(prices + [98, 96, 99, 101]))
    base_swings = {(e.type, e.time, e.price) for e in base.events if "SWING" in e.type}
    extended_swings = {(e.type, e.time, e.price) for e in extended.events if "SWING" in e.type}
    assert base_swings <= extended_swings


def test_incomplete_candle_is_excluded() -> None:
    dataset = _dataset([100 + ((i % 5) * 2) for i in range(40)])
    forming = Candle(timestamp=dataset.candles[-1].timestamp + timedelta(hours=1), open=100, high=103, low=99, close=102, volume=1000, symbol="BTC/USDT", timeframe=Timeframe.HOUR_1, source="test", is_complete=False)
    dataset = dataset.model_copy(update={"candles": dataset.candles + (forming,)})
    result = analyze_market_structure(dataset)
    assert result.latest_candle_timestamp == dataset.candles[-2].timestamp


def test_requires_minimum_history() -> None:
    with pytest.raises(ValueError, match="30 completed candles"):
        analyze_market_structure(_dataset([100 + i for i in range(29)]))


def test_bos_then_choch_uses_close_through_confirmed_levels() -> None:
    dataset = _ohlc_dataset([(100, 101, 99, 100)] * 4 + [(104, 107, 103, 106), (106, 107, 104, 106), (96, 97, 93, 94), (94, 95, 92, 93)])
    events = _structure_breaks(list(dataset.candles), [(2, "HIGH", 105.0)], [(2, "LOW", 95.0)])
    assert [event.type for event in events] == ["BOS_BULLISH", "CHOCH_BEARISH"]
    assert all(event.time >= event.source_candles[-1] for event in events)


def test_equal_high_and_low_create_liquidity_levels() -> None:
    rows = list(_dataset([100 + (i % 2) for i in range(20)]).candles)
    events = _equal_levels(rows, [(2, "HIGH", 105.0), (8, "HIGH", 105.05)], [(4, "LOW", 95.0), (10, "LOW", 95.04)])
    assert {event.type for event in events} == {"EQUAL_HIGH", "EQUAL_LOW"}


def test_liquidity_sweep_requires_wick_beyond_level_and_close_back_inside() -> None:
    candles = [(100, 101, 99, 100)] * 8
    candles[2] = (100, 105, 99, 103)
    candles[6] = (100, 105.8, 99, 104.8)
    dataset = _ohlc_dataset(candles)
    rows = list(dataset.candles)
    level = _event("EQUAL_HIGH", 105.0, 4, rows, 1.0, invalidation=105.0, source_indexes=(2, 4))
    sweep = _liquidity_and_sweeps(rows, [level])[0]
    assert sweep.type == "LIQUIDITY_SWEEP_HIGH"
    assert sweep.source_candles[-1] == rows[6].timestamp and sweep.time == rows[6].timestamp


def test_liquidity_pool_and_stop_run_are_explicit_derived_events() -> None:
    rows = list(_ohlc_dataset([(100, 101, 99, 100)] * 8).candles)
    level = _event("EQUAL_HIGH", 105.0, 4, rows, 0.9, invalidation=105.0, source_indexes=(2, 4))
    sweep = _event("LIQUIDITY_SWEEP_HIGH", 105.0, 6, rows, 0.8, invalidation=106.0, source_indexes=(2, 4, 6))
    derived = _liquidity_extensions(rows, [level], [sweep])
    assert [event.type for event in derived] == ["LIQUIDITY_POOL_HIGH", "STOP_RUN_HIGH"]
    assert derived[0].time == rows[4].timestamp and derived[1].time == rows[6].timestamp


def test_displacement_and_order_block_are_linked() -> None:
    candles = [(100, 101, 99, 100)] * 15
    candles[13] = (102, 103, 98, 99)
    candles[14] = (99, 108, 98, 107)
    rows = list(_ohlc_dataset(candles).candles)
    displacement = _displacement(rows)
    assert any(event.type == "DISPLACEMENT_BULLISH" for event in displacement)
    blocks = _order_blocks(rows, displacement)
    block = next(event for event in blocks if event.type == "ORDER_BLOCK_BULLISH")
    assert block.source_candles == (rows[13].timestamp, rows[14].timestamp)


def test_fvg_detects_three_candle_gap_with_causal_provenance() -> None:
    rows = list(_ohlc_dataset([(100, 102, 99, 101), (101, 106, 100, 105), (105, 109, 104, 108)]).candles)
    event = _fvg(rows)[0]
    assert event.type == "FVG_BULLISH"
    assert event.source_candles == tuple(rows[i].timestamp for i in (0, 1, 2))
    assert event.time == rows[2].timestamp


def test_premium_discount_uses_latest_confirmed_swing_range() -> None:
    rows = list(_dataset([100 + ((i % 3) - 1) for i in range(30)]).candles)
    events = _zone_events(rows, [(10, "HIGH", 120.0)], [(8, "LOW", 100.0)])
    assert len(events) == 1
    assert events[0].type in {"PREMIUM", "DISCOUNT"}
    assert events[0].source_candles == (rows[8].timestamp, rows[10].timestamp, rows[12].timestamp)


def test_inducement_requires_directionally_matching_sweep_and_break() -> None:
    rows = list(_dataset([100 + ((i % 3) - 1) for i in range(30)]).candles)
    sweep = _event("LIQUIDITY_SWEEP_LOW", 95.0, 10, rows, 0.8, invalidation=94.0)
    bullish = _event("BOS_BULLISH", 105.0, 14, rows, 0.7, invalidation=103.0, source_indexes=(8, 14))
    bearish = _event("BOS_BEARISH", 95.0, 14, rows, 0.7, invalidation=97.0, source_indexes=(8, 14))
    assert [e.type for e in _inducement(rows, [sweep], [bullish])] == ["INDUCEMENT_BULLISH"]
    assert _inducement(rows, [sweep], [bearish]) == []


def test_status_semantics_distinguish_active_invalidated_and_broken() -> None:
    rows = list(_dataset([100 + ((i % 3) - 1) for i in range(30)]).candles)
    active_fvg = _event("FVG_BULLISH", 105.0, 20, rows, 0.8, invalidation=95.0)
    invalidated_fvg = _event("FVG_BULLISH", 105.0, 20, rows, 0.8, invalidation=101.0)
    broken_pool = _event("LIQUIDITY_POOL_HIGH", 110.0, 20, rows, 0.8, invalidation=110.0)
    sweep = _event("LIQUIDITY_SWEEP_HIGH", 110.0, 22, rows, 0.8, invalidation=112.0)
    statuses = _apply_snapshot_statuses([active_fvg, invalidated_fvg, broken_pool, sweep], rows)
    assert statuses[0].status is StructureStatus.ACTIVE
    assert statuses[1].status is StructureStatus.INVALIDATED
    assert statuses[2].status is StructureStatus.BROKEN
    assert statuses[3].status is StructureStatus.CONFIRMED


def test_event_factory_rejects_future_source_candles() -> None:
    rows = list(_dataset([100 + i for i in range(30)]).candles)
    with pytest.raises(ValueError, match="after its detection time"):
        _event("TEST", 110.0, 10, rows, 0.5, source_indexes=(10, 11))
