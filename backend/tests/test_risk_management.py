from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Candle, OHLCVDataset, TechnicalAnalysisResult
from app.models.mtf import MTFBias, MTFResearchConclusion, MTFState, MTFTimeframeAnalysis, MultiTimeframeResult
from app.models.risk import RiskPolicy, RiskQualificationStatus
from app.models.strategy import SignalDirection, StrategyPortfolioResult, StrategySignal, StrategyStatus
from app.models.strategy_selection import QualificationStatus, StrategyQualification, StrategySelectionResult
from app.services.risk_management import qualify_position

UTC = timezone.utc
NOW = datetime(2026, 9, 3, tzinfo=UTC)


def make_selection(direction: SignalDirection = SignalDirection.LONG) -> StrategySelectionResult:
    items = tuple(
        MTFTimeframeAnalysis(
            timeframe=tf,
            bias=MTFBias.BULLISH,
            state=state,
            conclusion="test",
            confidence=0.9,
            latest_candle_timestamp=NOW,
            source="test",
            candle_count=250,
        )
        for tf, state in (
            ("1d", MTFState.DAILY_BIAS),
            ("4h", MTFState.H4_TREND),
            ("1h", MTFState.H1_PULLBACK),
            ("15m", MTFState.M15_BULLISH_BOS),
        )
    )
    mtf = MultiTimeframeResult(
        symbol="BTC/USD",
        calculated_at=NOW,
        timeframes=items,
        research=MTFResearchConclusion(
            alignment_count=4,
            bias=MTFBias.BULLISH,
            confidence=0.9,
            primary_setup="H1 demand + M15 bullish BOS",
            invalidation="H1 structure break",
            conclusion="test",
        ),
    )
    signal = StrategySignal(
        strategy_id="momentum",
        strategy_version="1.0.0",
        symbol="BTC/USD",
        timeframe="15m",
        generated_at=NOW,
        source="test",
        direction=direction,
        confidence=0.9,
        status=StrategyStatus.ACTIVE,
        regime="STRONG_TREND_UP",
        regime_compatible=True,
        rationale="test",
    )
    portfolio = StrategyPortfolioResult(
        symbol="BTC/USD",
        timeframe="15m",
        source="test",
        generated_at=NOW,
        regime="STRONG_TREND_UP",
        regime_confidence=0.9,
        strategies=(signal,),
        active_strategy_count=1,
    )
    return StrategySelectionResult(
        symbol="BTC/USD",
        generated_at=NOW,
        mtf=mtf,
        qualifications=(StrategyQualification(
            strategy_id="momentum",
            strategy_version="1.0.0",
            direction=direction,
            status=QualificationStatus.QUALIFIED,
            score=0.90,
            mtf_bias=MTFBias.BULLISH,
            mtf_alignment_count=4,
            mtf_gate_passed=True,
            reasons=("test",),
        ),),
        selected_strategy_id="momentum",
        selected_direction=direction,
        selected_score=0.90,
        decision="STRATEGY_SELECTED",
    )


def make_dataset(close: float = 100.0) -> OHLCVDataset:
    candles = []
    start = NOW - timedelta(hours=19)
    for index in range(20):
        price = close + index * 0.1
        candles.append(Candle(
            timestamp=start + timedelta(hours=index),
            open=price,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=100.0,
            symbol="BTC/USD",
            timeframe="1h",
            source="test",
            is_complete=True,
        ))
    return OHLCVDataset(symbol="BTC/USD", timeframe="1h", source="test", requested_at=NOW, candles=tuple(candles))


def make_features(atr: float = 2.0) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        symbol="BTC/USD",
        timeframe="1h",
        source="test",
        calculated_at=NOW,
        latest_candle_timestamp=NOW,
        candle_count=20,
        indicators={"atr14": atr},
    )


def test_long_position_uses_equity_risk_and_atr_stop() -> None:
    result = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)

    assert result.status is RiskQualificationStatus.QUALIFIED
    assert result.risk_amount == pytest.approx(75.0)
    assert result.entry_price == pytest.approx(101.9)
    assert result.stop_distance == pytest.approx(3.0)
    assert result.stop_loss == pytest.approx(98.9)
    assert result.take_profit == pytest.approx(107.9)
    assert result.position_size == pytest.approx(25.0)
    assert result.reward_risk == pytest.approx(2.0)


def test_short_position_inverts_stop_and_target() -> None:
    result = qualify_position(
        make_selection(SignalDirection.SHORT),
        make_dataset(),
        make_features(),
        10_000,
        RiskPolicy(),
    )

    assert result.status is RiskQualificationStatus.QUALIFIED
    assert result.stop_loss == pytest.approx(104.9)
    assert result.take_profit == pytest.approx(95.9)


def test_invalid_equity_is_rejected_before_sizing() -> None:
    with pytest.raises(ValueError, match="account_equity"):
        qualify_position(make_selection(), make_dataset(), make_features(), 0)


def test_missing_atr_is_rejected() -> None:
    with pytest.raises(ValueError, match="ATR14"):
        qualify_position(make_selection(), make_dataset(), make_features(atr=0), 10_000)
