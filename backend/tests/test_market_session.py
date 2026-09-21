from datetime import datetime, timedelta, timezone

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.services.market_session import build_session_state


def _dataset() -> OHLCVDataset:
    start = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    candles = []
    price = 100.0
    for index in range(96):
        timestamp = start + timedelta(hours=index)
        amplitude = 0.5 + (index % 8) * 0.08
        candles.append(
            Candle(
                timestamp=timestamp,
                open=price,
                high=price + amplitude,
                low=price - amplitude,
                close=price + 0.2,
                volume=1000,
                symbol="BTC/USDT",
                timeframe=Timeframe.HOUR_1,
                source="test",
                is_complete=True,
            )
        )
        price += 0.2
    return OHLCVDataset(
        symbol="BTC/USDT",
        timeframe=Timeframe.HOUR_1,
        source="test",
        requested_at=start,
        candles=tuple(candles),
    )


def test_crypto_is_continuous_and_uses_activity_window():
    state = build_session_state(
        asset_class="crypto",
        now=datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc),
        market_open=True,
        dataset=_dataset(),
        symbol="BTC/USDT",
    )

    assert state.status == "OPEN"
    assert state.market_open is True
    assert state.phase == "US_ACTIVITY"
    assert state.volatility_score is not None
    assert 0 <= state.volatility_score <= 100


def test_forex_uses_london_new_york_overlap():
    state = build_session_state(
        asset_class="forex",
        now=datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc),
        market_open=True,
        dataset=None,
        symbol="EURUSD",
    )

    assert state.status == "OPEN"
    assert state.phase == "OVERLAP"
    assert state.label == "London / New York Overlap"


def test_forex_weekend_is_closed():
    state = build_session_state(
        asset_class="forex",
        now=datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc),
        market_open=False,
        dataset=None,
        symbol="EURUSD",
    )

    assert state.status == "CLOSED"
    assert state.phase == "CLOSED"


def test_stocks_use_core_session():
    state = build_session_state(
        asset_class="stocks",
        now=datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc),
        market_open=True,
        dataset=None,
        symbol="SPY",
    )

    assert state.status == "OPEN"
    assert state.phase == "CORE"
    assert state.label == "US Core Session"


def test_closed_stock_market_is_distinct_from_low_volatility():
    state = build_session_state(
        asset_class="stocks",
        now=datetime(2026, 9, 21, 23, 0, tzinfo=timezone.utc),
        market_open=False,
        dataset=None,
        symbol="SPY",
    )

    assert state.status == "CLOSED"
    assert state.phase == "CLOSED"
    assert state.label == "Market Closed"
