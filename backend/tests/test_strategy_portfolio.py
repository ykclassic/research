from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, TechnicalAnalysisResult, Timeframe
from app.models.regime import MarketRegime, MarketRegimeResult, RegimeEvidence, RegimeThresholds
from app.models.strategy import SignalDirection, StrategyStatus
from app.services.strategy_portfolio import StrategyPortfolio, evaluate_strategy_portfolio


UTC = timezone.utc


def make_dataset(count: int = 220, complete: bool = True) -> OHLCVDataset:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for index in range(count):
        close = 100.0 + index * 0.5
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=close - 0.2,
                high=close + 0.4,
                low=close - 0.4,
                close=close,
                volume=1_000.0,
                symbol="BTC/USD",
                timeframe=Timeframe.HOUR_1,
                source="test",
                is_complete=complete or index < count - 1,
            )
        )
    return OHLCVDataset(
        symbol="BTC/USD",
        timeframe=Timeframe.HOUR_1,
        source="test",
        requested_at=start + timedelta(hours=count),
        provider_timestamp=start + timedelta(hours=count - 1),
        candles=tuple(candles),
    )


def make_features(dataset: OHLCVDataset) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
        calculated_at=datetime.now(UTC),
        latest_candle_timestamp=dataset.latest_candle.timestamp,
        candle_count=len(dataset.completed_candles),
        indicators={
            "ema20": 195.0,
            "ema50": 180.0,
            "ema200": 140.0,
            "adx14": 30.0,
            "rsi14": 55.0,
            "bb_lower": 180.0,
            "bb_upper": 220.0,
            "bb_width": 0.2,
            "macd": 2.0,
            "macd_signal": 1.0,
            "macd_histogram": 1.0,
            "atr14": 1.5,
        },
    )


def make_regime(dataset: OHLCVDataset, regime: MarketRegime = MarketRegime.STRONG_TREND_UP) -> MarketRegimeResult:
    return MarketRegimeResult(
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        source=dataset.source,
        calculated_at=datetime.now(UTC),
        provider_timestamp=dataset.provider_timestamp,
        latest_candle_timestamp=dataset.latest_candle.timestamp,
        candle_count=len(dataset.completed_candles),
        regime=regime,
        confidence=0.9,
        evidence=RegimeEvidence(
            price=209.5,
            ema_50=180.0,
            ema_200=140.0,
            price_above_ema_200=True,
            ema_50_above_ema_200=True,
            adx=30.0,
            atr=1.5,
            atr_percent=0.7,
            atr_percentile=0.7,
            bb_width=0.2,
            bb_width_percentile=0.7,
            trend_direction="UP",
            trend_persistence=0.8,
            directional_move_ratio=0.7,
        ),
        thresholds=RegimeThresholds(),
        rule_id="R2",
        rule="test",
    )


def test_portfolio_evaluates_all_registered_strategies_without_selection() -> None:
    dataset = make_dataset()
    result = evaluate_strategy_portfolio(dataset, make_features(dataset), make_regime(dataset))

    assert len(result.strategies) == 4
    assert {signal.strategy_id for signal in result.strategies} == {
        "trend_following",
        "mean_reversion",
        "momentum",
        "breakout",
    }
    assert result.active_strategy_count == 4
    assert result.strategies[0].direction is SignalDirection.LONG
    assert result.strategies[0].status is StrategyStatus.ACTIVE


def test_portfolio_rejects_snapshot_mismatch() -> None:
    dataset = make_dataset()
    features = make_features(dataset)
    regime = make_regime(dataset)
    mismatch = features.model_copy(update={"latest_candle_timestamp": dataset.candles[-2].timestamp})

    with pytest.raises(ValueError, match="same latest completed candle"):
        StrategyPortfolio().evaluate(dataset, mismatch, regime)


def test_portfolio_rejects_forming_latest_candle() -> None:
    dataset = make_dataset(complete=False)
    features = make_features(dataset)
    regime = make_regime(dataset)

    with pytest.raises(ValueError, match="completed latest candle"):
        StrategyPortfolio().evaluate(dataset, features, regime)


def test_mean_reversion_is_not_active_in_strong_trend() -> None:
    dataset = make_dataset()
    features = make_features(dataset).model_copy(
        update={
            "indicators": {
                **make_features(dataset).indicators,
                "rsi14": 20.0,
                "bb_lower": 210.0,
            }
        }
    )
    result = evaluate_strategy_portfolio(dataset, features, make_regime(dataset))
    signal = next(item for item in result.strategies if item.strategy_id == "mean_reversion")

    assert signal.direction is SignalDirection.NEUTRAL
    assert signal.regime_compatible is False
    assert signal.status is StrategyStatus.ACTIVE
