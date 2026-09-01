from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user_or_github_actions
from app.api.regime import quote_service
from app.main import app
from app.models import Timeframe
from app.models.market import Candle, OHLCVDataset
from app.models.regime import MarketRegime, RegimeThresholds
from app.services import regime_detection
from app.services.regime_detection import detect_regime


SYMBOL = "BTC/USD"
SOURCE = "synthetic"


def make_dataset(count: int = 220) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(count):
        price = 100.0 + index * 0.1
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=price - 0.1,
                high=price + 0.2,
                low=price - 0.2,
                close=price,
                volume=1000.0,
                symbol=SYMBOL,
                timeframe=Timeframe.HOUR_1,
                source=SOURCE,
                is_complete=True,
            )
        )
    return OHLCVDataset(
        symbol=SYMBOL,
        timeframe=Timeframe.HOUR_1,
        source=SOURCE,
        requested_at=datetime.now(timezone.utc),
        provider_timestamp=candles[-1].timestamp,
        candles=tuple(candles),
    )


def patch_evidence(monkeypatch, *, direction="UP", persistence=0.80, ratio=0.60, adx=30.0,
                   atr_percentile=0.50, bb_percentile=0.50, bullish=True):
    monkeypatch.setattr(regime_detection, "_trend_metrics", lambda closes: (direction, persistence, ratio))
    monkeypatch.setattr(regime_detection, "_atr_percent_series", lambda candles: [0.01] * 100 + [0.02])
    monkeypatch.setattr(regime_detection, "_bb_width_series", lambda closes: [0.01] * 100 + [0.02])
    monkeypatch.setattr(
        regime_detection,
        "calculate_indicators",
        lambda candles: {
            "adx14": adx,
            "atr14": 2.0,
            "ema50": 110.0 if bullish else 90.0,
            "ema200": 100.0,
            "bb_width": 0.02,
        },
    )

    # Percentile helpers are patched separately because the production helper
    # derives percentile from its observations.
    calls = iter([atr_percentile, bb_percentile])
    monkeypatch.setattr(regime_detection, "_percentile_rank", lambda values, current: next(calls))


def test_evidence_contains_thresholds_and_provenance(monkeypatch):
    patch_evidence(monkeypatch, direction="UP", persistence=0.80, ratio=0.60, adx=30.0, bullish=True)
    result = detect_regime(make_dataset())

    assert result.regime is MarketRegime.STRONG_TREND_UP
    assert result.confidence == pytest.approx(result.confidence)
    assert 0.0 <= result.confidence <= 1.0
    assert result.rule_id == "R2"
    assert result.thresholds == RegimeThresholds()
    assert result.evidence.adx == 30.0
    assert result.evidence.trend_persistence == pytest.approx(0.80)
    assert result.evidence.directional_move_ratio == pytest.approx(0.60)
    assert result.latest_candle_timestamp == make_dataset().latest_candle.timestamp


def test_strong_trend_thresholds_are_inclusive(monkeypatch):
    patch_evidence(monkeypatch, direction="UP", persistence=0.70, ratio=0.55, adx=25.0, bullish=True)
    assert detect_regime(make_dataset()).regime is MarketRegime.STRONG_TREND_UP


def test_below_strong_threshold_becomes_weak_trend_when_aligned(monkeypatch):
    patch_evidence(monkeypatch, direction="UP", persistence=0.50, ratio=0.25, adx=24.99, bullish=True)
    assert detect_regime(make_dataset()).regime is MarketRegime.WEAK_TREND


def test_range_threshold_is_strictly_below_weak_directional_ratio(monkeypatch):
    patch_evidence(monkeypatch, direction="FLAT", persistence=0.50, ratio=0.249999, adx=10.0, bullish=False)
    assert detect_regime(make_dataset()).regime is MarketRegime.RANGE


def test_high_volatility_threshold_is_inclusive(monkeypatch):
    patch_evidence(monkeypatch, direction="FLAT", persistence=0.50, ratio=0.10, adx=10.0,
                   atr_percentile=0.80, bb_percentile=0.50, bullish=False)
    assert detect_regime(make_dataset()).regime is MarketRegime.HIGH_VOLATILITY


def test_low_volatility_threshold_is_inclusive(monkeypatch):
    patch_evidence(monkeypatch, direction="FLAT", persistence=0.50, ratio=0.10, adx=10.0,
                   atr_percentile=0.20, bb_percentile=0.20, bullish=False)
    assert detect_regime(make_dataset()).regime is MarketRegime.LOW_VOLATILITY


def test_unknown_is_explicit_for_directional_ema_conflict(monkeypatch):
    patch_evidence(monkeypatch, direction="UP", persistence=0.80, ratio=0.60, adx=30.0, bullish=False)
    assert detect_regime(make_dataset()).regime is MarketRegime.UNKNOWN
    assert detect_regime(make_dataset()).rule_id == "R1"


def test_forming_candle_is_rejected_even_when_enough_completed_history_exists(monkeypatch):
    dataset = make_dataset()
    candles = list(dataset.candles)
    candles[-1] = candles[-1].model_copy(update={"is_complete": False})
    invalid = dataset.model_copy(update={"candles": tuple(candles)})
    with pytest.raises(ValueError, match="completed candles only"):
        detect_regime(invalid)


@pytest.fixture()
def authenticated_client(monkeypatch):
    app.dependency_overrides[get_current_user_or_github_actions] = lambda: {"id": "u1"}
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user_or_github_actions, None)


def test_regime_api_returns_deterministic_evidence(authenticated_client, monkeypatch):
    dataset = make_dataset()

    async def fake_get_candles(symbol, timeframe, limit):
        assert symbol == SYMBOL
        assert timeframe is Timeframe.HOUR_1
        assert limit == 250
        return dataset

    monkeypatch.setattr(quote_service.provider, "get_candles", fake_get_candles)
    monkeypatch.setattr(regime_detection, "_trend_metrics", lambda closes: ("UP", 0.80, 0.60))
    monkeypatch.setattr(regime_detection, "_atr_percent_series", lambda candles: [0.01] * 100 + [0.02])
    monkeypatch.setattr(regime_detection, "_bb_width_series", lambda closes: [0.01] * 100 + [0.02])
    monkeypatch.setattr(regime_detection, "_percentile_rank", lambda values, current: 0.50)
    monkeypatch.setattr(
        regime_detection,
        "calculate_indicators",
        lambda candles: {"adx14": 30.0, "atr14": 2.0, "ema50": 110.0, "ema200": 100.0, "bb_width": 0.02},
    )

    response = authenticated_client.get("/api/regime/BTC%2FUSD", params={"timeframe": "1h", "limit": 250})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["regime"] == "STRONG_TREND_UP"
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["source"] == SOURCE
    assert body["candle_count"] == 220
    assert body["rule_id"] == "R2"
    assert body["thresholds"]["adx_strong"] == 25.0
    assert body["evidence"]["trend_persistence"] == 0.8
    assert body["evidence"]["directional_move_ratio"] == 0.6


def test_regime_api_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/api/regime/BTC%2FUSD")
    assert response.status_code == 401
