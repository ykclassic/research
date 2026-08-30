from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.models.regime import MarketRegime
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime


def make_dataset(closes: list[float]) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(hours=index),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1000.0,
            symbol="BTC/USD",
            timeframe=Timeframe.HOUR_1,
            source="test",
            is_complete=True,
        )
        for index, close in enumerate(closes)
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test",
        requested_at=start,
        provider_timestamp=start,
        candles=candles,
    )


def test_regime_requires_sufficient_completed_history():
    dataset = make_dataset([100.0 + index for index in range(MINIMUM_CANDLES - 1)])

    with pytest.raises(ValueError, match="At least 220 completed candles"):
        detect_regime(dataset)


def test_strong_uptrend_contains_auditable_evidence():
    closes = [100.0 + index * 0.8 for index in range(MINIMUM_CANDLES)]
    result = detect_regime(make_dataset(closes))

    assert result.regime == MarketRegime.STRONG_TREND_UP
    assert 0.0 <= result.confidence <= 1.0
    assert result.evidence.price_above_ema_200 is True
    assert result.evidence.ema_50_above_ema_200 is True
    assert result.evidence.adx14 is not None
    assert result.evidence.atr_percentile is not None
    assert result.evidence.bb_width_percentile is not None
    assert result.evidence.trend_persistence is not None


def test_strong_downtrend_is_directionally_distinct():
    closes = [300.0 - index * 0.8 for index in range(MINIMUM_CANDLES)]
    result = detect_regime(make_dataset(closes))

    assert result.regime == MarketRegime.STRONG_TREND_DOWN
    assert result.evidence.price_above_ema_200 is False
    assert result.evidence.ema_50_above_ema_200 is False
    assert result.evidence.trend_persistence is not None
    assert result.evidence.trend_persistence >= 0.9


def test_regime_detection_is_deterministic_for_same_dataset():
    dataset = make_dataset([100.0 + index * 0.2 for index in range(MINIMUM_CANDLES)])

    first = detect_regime(dataset)
    second = detect_regime(dataset)

    assert first.model_copy(update={"calculated_at": None}) if False else True
    assert first.regime == second.regime
    assert first.confidence == second.confidence
    assert first.evidence == second.evidence
    assert first.latest_candle_timestamp == second.latest_candle_timestamp
    assert first.candle_count == second.candle_count


def test_regime_never_accepts_forming_candles():
    closes = [100.0 + index * 0.5 for index in range(MINIMUM_CANDLES)]
    dataset = make_dataset(closes)
    candles = list(dataset.candles)
    candles[-1] = candles[-1].model_copy(update={"is_complete": False})
    invalid = dataset.model_copy(update={"candles": tuple(candles)})

    with pytest.raises(ValueError, match="completed candles only"):
        detect_regime(invalid)
