from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.models.regime import MarketRegime
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime


def make_dataset(closes: list[float], *, complete: bool = True) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(hours=index),
            open=close - 0.25,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1_000.0,
            symbol="BTC/USD",
            timeframe=Timeframe.HOUR_1,
            source="test",
            is_complete=complete,
        )
        for index, close in enumerate(closes)
    )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test",
        requested_at=start,
        candles=candles,
    )


def test_regime_never_accepts_forming_candles():
    closes = [100.0 + index * 0.5 for index in range(MINIMUM_CANDLES)]
    dataset = make_dataset(closes)
    candles = list(dataset.candles)
    candles[-1] = candles[-1].model_copy(update={"is_complete": False})
    invalid = dataset.model_copy(update={"candles": tuple(candles)})

    with pytest.raises(ValueError, match="completed candles only"):
        detect_regime(invalid)


def test_regime_rejects_forming_candle_even_when_enough_completed_history_exists():
    closes = [100.0 + index * 0.5 for index in range(MINIMUM_CANDLES + 1)]
    dataset = make_dataset(closes)
    candles = list(dataset.candles)
    candles[-1] = candles[-1].model_copy(update={"is_complete": False})
    invalid = dataset.model_copy(update={"candles": tuple(candles)})

    with pytest.raises(ValueError, match="completed candles only"):
        detect_regime(invalid)


def test_regime_requires_minimum_completed_history():
    dataset = make_dataset([100.0 + index * 0.5 for index in range(MINIMUM_CANDLES - 1)])

    with pytest.raises(ValueError, match="220 completed candles"):
        detect_regime(dataset)


def test_monotonic_uptrend_is_strong_trend_up_with_audit_evidence():
    dataset = make_dataset([100.0 + index * 0.5 for index in range(MINIMUM_CANDLES)])

    result = detect_regime(dataset)

    assert result.regime is MarketRegime.STRONG_TREND_UP
    assert 0.0 <= result.confidence <= 1.0
    assert result.evidence.price_above_ema_200 is True
    assert result.evidence.ema_50_above_ema_200 is True
    assert result.evidence.adx14 is not None
    assert result.evidence.atr14 is not None
    assert result.evidence.atr_percentile is not None
    assert result.evidence.bb_width_percentile is not None
    assert result.evidence.trend_persistence == 1.0
    assert result.evidence.structure_bias == "BULLISH"
    assert result.latest_completed_candle_timestamp == dataset.candles[-1].timestamp


def test_monotonic_downtrend_is_strong_trend_down_with_audit_evidence():
    dataset = make_dataset([300.0 - index * 0.5 for index in range(MINIMUM_CANDLES)])

    result = detect_regime(dataset)

    assert result.regime is MarketRegime.STRONG_TREND_DOWN
    assert result.evidence.price_above_ema_200 is False
    assert result.evidence.ema_50_above_ema_200 is False
    assert result.evidence.trend_persistence == 1.0
    assert result.evidence.structure_bias == "BEARISH"


def test_regime_result_is_provenance_aware_and_json_serializable():
    dataset = make_dataset([100.0 + index * 0.5 for index in range(MINIMUM_CANDLES)])

    result = detect_regime(dataset)
    payload = result.model_dump(mode="json")

    assert payload["symbol"] == "BTC/USD"
    assert payload["timeframe"] == "1h"
    assert payload["source"] == "test"
    assert payload["regime"] == "STRONG_TREND_UP"
    assert "evidence" in payload
    assert "rationale" in payload
