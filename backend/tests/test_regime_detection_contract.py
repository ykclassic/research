from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.models.regime import MarketRegime
from app.services.regime_detection import MINIMUM_CANDLES, detect_regime


def make_dataset(closes: list[float], complete: bool = True) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index, close in enumerate(closes):
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=close - 0.25,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1000.0,
                symbol="BTC/USD",
                timeframe=Timeframe.HOUR_1,
                source="test",
                is_complete=complete,
            )
        )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test",
        requested_at=datetime.now(timezone.utc),
        candles=tuple(candles),
    )


def test_regime_requires_completed_candles_only() -> None:
    dataset = make_dataset([100.0 + index * 0.5 for index in range(MINIMUM_CANDLES)])
    candles = list(dataset.candles)
    candles[-1] = candles[-1].model_copy(update={"is_complete": False})
    invalid = dataset.model_copy(update={"candles": tuple(candles)})

    with pytest.raises(ValueError, match="completed candles only"):
        detect_regime(invalid)


def test_regime_requires_minimum_history() -> None:
    dataset = make_dataset([100.0 + index * 0.5 for index in range(MINIMUM_CANDLES - 1)])

    with pytest.raises(ValueError, match="220 completed candles"):
        detect_regime(dataset)


def test_regime_result_is_evidence_backed_and_serializable() -> None:
    dataset = make_dataset([100.0 + index * 0.5 for index in range(MINIMUM_CANDLES)])
    result = detect_regime(dataset)

    assert isinstance(result.regime, MarketRegime)
    assert 0.0 <= result.confidence <= 1.0
    assert result.candle_count == MINIMUM_CANDLES
    assert result.latest_completed_candle_timestamp == dataset.candles[-1].timestamp
    assert result.ruleset_version == "5.1.0"
    assert result.evidence.price == dataset.candles[-1].close
    assert result.evidence.adx14 is not None
    assert result.evidence.atr14 is not None
    assert result.evidence.bb_width is not None
    assert result.evidence.trend_persistence is not None
    assert result.model_dump(mode="json")["regime"] == result.regime.value


def test_regime_is_deterministic_for_same_dataset() -> None:
    dataset = make_dataset([100.0 + ((index % 12) - 6) * 0.2 for index in range(MINIMUM_CANDLES)])
    first = detect_regime(dataset)
    second = detect_regime(dataset)

    assert first.regime == second.regime
    assert first.confidence == second.confidence
    assert first.evidence == second.evidence
