from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sin

import pytest

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.models.regime import MarketRegime
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime


def make_dataset(closes: list[float]) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close
        spread = max(close * 0.001, 0.01)
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=previous,
                high=max(previous, close) + spread,
                low=max(0.01, min(previous, close) - spread),
                close=close,
                volume=1_000.0,
                symbol="BTC/USD",
                timeframe=Timeframe.HOUR_1,
                source="synthetic",
                is_complete=True,
            )
        )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="synthetic",
        requested_at=start,
        candles=tuple(candles),
    )


def synthetic_series(kind: str, count: int = MINIMUM_CANDLES) -> list[float]:
    """Create deterministic paths with a distinct final-state regime."""
    price = 100.0
    series: list[float] = []
    for index in range(count):
        if kind == "strong_up":
            price += 0.8
        elif kind == "strong_down":
            price -= 0.5
            if price <= 1.0:
                price = 1.0 + index * 0.01
        elif kind == "weak_trend":
            price += 0.12 + 1.2 * (sin(index * 0.25) - sin((index - 1) * 0.25))
        elif kind == "range":
            price = 100.0 + 0.5 * sin(index * 0.12)
        elif kind == "high_volatility":
            step = 0.25 if index < count - 35 else (4.0 if index % 2 else -4.0)
            price = max(10.0, price + step)
        elif kind == "low_volatility":
            if index < count - 35:
                price += 0.04
            else:
                price = 108.2 + 0.03 * sin(index * 0.9)
        elif kind == "unknown":
            if index < count - 40:
                price -= 0.10
            else:
                price += 0.01
        else:
            raise AssertionError(kind)
        series.append(price)
    return series


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("strong_up", MarketRegime.STRONG_TREND_UP),
        ("strong_down", MarketRegime.STRONG_TREND_DOWN),
        ("weak_trend", MarketRegime.WEAK_TREND),
        ("range", MarketRegime.RANGE),
        ("high_volatility", MarketRegime.HIGH_VOLATILITY),
        ("low_volatility", MarketRegime.LOW_VOLATILITY),
        ("unknown", MarketRegime.UNKNOWN),
    ],
)
def test_each_regime_is_classified_from_controlled_synthetic_data(kind: str, expected: MarketRegime) -> None:
    dataset = make_dataset(synthetic_series(kind))
    result = detect_regime(dataset)
    assert result.regime == expected
    assert 0.0 <= result.confidence <= 1.0
    assert result.evidence.adx is not None
    assert result.evidence.atr is not None
    assert result.evidence.bb_width is not None
    assert result.evidence.trend_direction in {"UP", "DOWN", "NEUTRAL"}
    assert result.rule


def test_regime_classification_is_deterministic() -> None:
    dataset = make_dataset(synthetic_series("strong_up"))
    first = detect_regime(dataset)
    second = detect_regime(dataset)
    assert first.regime == second.regime
    assert first.confidence == second.confidence
    assert first.evidence.model_dump() == second.evidence.model_dump()


def test_regime_never_accepts_forming_candles() -> None:
    dataset = make_dataset(synthetic_series("strong_up"))
    candles = list(dataset.candles)
    candles[-1] = candles[-1].model_copy(update={"is_complete": False})
    invalid = dataset.model_copy(update={"candles": tuple(candles)})
    with pytest.raises(ValueError, match="completed candles only"):
        detect_regime(invalid)


def test_regime_rejects_insufficient_history() -> None:
    dataset = make_dataset(synthetic_series("strong_up", MINIMUM_CANDLES - 1))
    with pytest.raises(ValueError, match="completed candles"):
        detect_regime(dataset)
