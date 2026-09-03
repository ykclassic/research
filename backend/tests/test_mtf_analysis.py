from datetime import datetime, timedelta, timezone

from app.models.market import Candle, CompletenessStatus, OHLCVDataset, Timeframe
from app.models.market_structure import StructureEvent, StructureStatus
from app.models.mtf import MTFBias, MTFState
from app.services.mtf_analysis import REQUIRED_TIMEFRAMES, analyze_multi_timeframe


def _dataset(timeframe: Timeframe, count: int = 220, *, bullish: bool = True) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    step = 0.35 if bullish else -0.35
    for index in range(count):
        previous = price
        price += step
        rows.append(
            Candle(
                timestamp=start + timedelta(seconds=timeframe.seconds * index),
                open=previous,
                high=max(previous, price) + 0.2,
                low=min(previous, price) - 0.2,
                close=price,
                volume=1000,
                symbol="BTC/USDT",
                timeframe=timeframe,
                source="fixture",
                is_complete=True,
            )
        )
    return OHLCVDataset(
        symbol="BTC/USDT",
        timeframe=timeframe,
        source="fixture",
        requested_at=start,
        candles=tuple(rows),
        completeness_status=CompletenessStatus.COMPLETE,
    )


def _event(timeframe: Timeframe, kind: str, price: float, *, status: StructureStatus = StructureStatus.CONFIRMED, invalidation: float | None = None) -> StructureEvent:
    timestamp = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return StructureEvent(
        type=kind,
        price=price,
        time=timestamp,
        timeframe=timeframe,
        strength=0.9,
        status=status,
        invalidation=invalidation,
        source_candles=(timestamp,),
    )


def test_required_hierarchy_is_daily_h4_h1_m15() -> None:
    assert REQUIRED_TIMEFRAMES == (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15)


def test_bullish_four_of_four_research_conclusion() -> None:
    datasets = {timeframe: _dataset(timeframe) for timeframe in REQUIRED_TIMEFRAMES}
    structures = {
        Timeframe.DAY_1: (_event(Timeframe.DAY_1, "BOS_BULLISH", 170.0),),
        Timeframe.HOUR_4: (_event(Timeframe.HOUR_4, "BOS_BULLISH", 170.0),),
        Timeframe.HOUR_1: (_event(Timeframe.HOUR_1, "ORDER_BLOCK_BULLISH", 176.0, status=StructureStatus.ACTIVE, invalidation=175.0),),
        Timeframe.MINUTE_15: (_event(Timeframe.MINUTE_15, "BOS_BULLISH", 177.0),),
    }
    result = analyze_multi_timeframe(datasets, structures)
    assert [item.timeframe for item in result.timeframes] == list(REQUIRED_TIMEFRAMES)
    assert result.research.alignment_count == 4
    assert result.research.bias is MTFBias.BULLISH
    assert result.research.primary_setup == "H1 demand + M15 bullish BOS"
    assert result.research.invalidation == "H1 structure break"
    assert result.research.confidence > 0.70
    assert result.timeframes[2].state is MTFState.H1_PULLBACK
    assert result.timeframes[3].state is MTFState.M15_BULLISH_BOS


def test_conflicting_timeframes_reduce_alignment() -> None:
    datasets = {timeframe: _dataset(timeframe) for timeframe in REQUIRED_TIMEFRAMES}
    structures = {
        Timeframe.DAY_1: (_event(Timeframe.DAY_1, "BOS_BULLISH", 170.0),),
        Timeframe.HOUR_4: (_event(Timeframe.HOUR_4, "BOS_BEARISH", 170.0),),
        Timeframe.HOUR_1: (_event(Timeframe.HOUR_1, "ORDER_BLOCK_BEARISH", 176.0, status=StructureStatus.ACTIVE, invalidation=177.0),),
        Timeframe.MINUTE_15: (_event(Timeframe.MINUTE_15, "BOS_BEARISH", 177.0),),
    }
    result = analyze_multi_timeframe(datasets, structures)
    assert result.research.alignment_count < 4
    assert result.research.primary_setup != "H1 demand + M15 bullish BOS"


def test_h1_pullback_requires_active_demand_overlap() -> None:
    datasets = {timeframe: _dataset(timeframe) for timeframe in REQUIRED_TIMEFRAMES}
    structures = {
        Timeframe.DAY_1: (),
        Timeframe.HOUR_4: (),
        Timeframe.HOUR_1: (_event(Timeframe.HOUR_1, "ORDER_BLOCK_BULLISH", 200.0, status=StructureStatus.ACTIVE, invalidation=199.0),),
        Timeframe.MINUTE_15: (),
    }
    result = analyze_multi_timeframe(datasets, structures)
    assert result.timeframes[2].state is not MTFState.H1_PULLBACK
