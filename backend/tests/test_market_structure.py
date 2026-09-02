from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, CompletenessStatus, OHLCVDataset, Timeframe
from app.models.market_structure import StructureStatus
from app.services.market_structure import analyze_market_structure


def _dataset(prices: list[float], *, source: str = "test") -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i, close in enumerate(prices):
        previous = prices[i - 1] if i else close
        high = max(close, previous) + 0.8
        low = min(close, previous) - 0.8
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=i),
                open=previous,
                high=high,
                low=low,
                close=close,
                volume=1000,
                symbol="BTC/USDT",
                timeframe=Timeframe.HOUR_1,
                source=source,
                is_complete=True,
            )
        )
    return OHLCVDataset(
        symbol="BTC/USDT",
        timeframe=Timeframe.HOUR_1,
        source=source,
        requested_at=start,
        candles=tuple(candles),
        completeness_status=CompletenessStatus.COMPLETE,
    )


def test_market_structure_emits_required_audit_fields() -> None:
    prices = [100, 102, 104, 102, 100, 103, 106, 104, 101, 105, 109, 107] * 4
    result = analyze_market_structure(_dataset(prices))
    assert result.events
    for event in result.events:
        assert event.type
        assert event.price > 0
        assert event.time.tzinfo is not None
        assert event.timeframe is Timeframe.HOUR_1
        assert 0 <= event.strength <= 1
        assert isinstance(event.status, StructureStatus)
        assert event.source_candles
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
    forming = Candle(
        timestamp=dataset.candles[-1].timestamp + timedelta(hours=1),
        open=100,
        high=103,
        low=99,
        close=102,
        volume=1000,
        symbol="BTC/USDT",
        timeframe=Timeframe.HOUR_1,
        source="test",
        is_complete=False,
    )
    dataset = dataset.model_copy(update={"candles": dataset.candles + (forming,)})
    result = analyze_market_structure(dataset)
    assert result.latest_candle_timestamp == dataset.candles[-2].timestamp


def test_requires_minimum_history() -> None:
    with pytest.raises(ValueError, match="30 completed candles"):
        analyze_market_structure(_dataset([100 + i for i in range(29)]))
