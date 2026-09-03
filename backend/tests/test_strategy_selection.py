from datetime import datetime, timezone

from app.models.mtf import MTFBias, MTFResearchConclusion, MTFState, MTFTimeframeAnalysis, MultiTimeframeResult
from app.models.strategy import SignalDirection, StrategySignal, StrategyStatus
from app.models.strategy_selection import QualificationStatus
from app.services.strategy_selection import select_strategy

UTC = timezone.utc
NOW = datetime(2026, 9, 3, tzinfo=UTC)


def make_mtf(alignment: int = 4, bias: MTFBias = MTFBias.BULLISH, confirmation: bool = True) -> MultiTimeframeResult:
    states = [MTFState.DAILY_BIAS, MTFState.H4_TREND, MTFState.H1_PULLBACK, MTFState.M15_BULLISH_BOS if confirmation else MTFState.M15_NEUTRAL]
    biases = [bias, bias, bias, bias if confirmation else MTFBias.NEUTRAL]
    items = []
    for index, (state, item_bias) in enumerate(zip(states, biases)):
        items.append(MTFTimeframeAnalysis(timeframe=("1d", "4h", "1h", "15m")[index], bias=item_bias, state=state, conclusion="test", confidence=0.9, latest_candle_timestamp=NOW, source="test", candle_count=250))
    return MultiTimeframeResult(symbol="BTC/USD", calculated_at=NOW, timeframes=tuple(items), research=MTFResearchConclusion(alignment_count=alignment, bias=bias, confidence=0.9, primary_setup="H1 demand + M15 bullish BOS", invalidation="H1 structure break", conclusion="test"))


def signal(strategy_id: str, confidence: float, direction: SignalDirection = SignalDirection.LONG) -> StrategySignal:
    return StrategySignal(strategy_id=strategy_id, strategy_version="1.0.0", symbol="BTC/USD", timeframe="15m", generated_at=NOW, source="test", direction=direction, confidence=confidence, status=StrategyStatus.ACTIVE, regime="STRONG_TREND_UP", regime_compatible=True, rationale="test")


def test_four_of_four_mtf_gate_selects_highest_scoring_strategy() -> None:
    from app.models.strategy import StrategyPortfolioResult

    portfolio = StrategyPortfolioResult(symbol="BTC/USD", timeframe="15m", source="test", generated_at=NOW, regime="STRONG_TREND_UP", regime_confidence=0.9, strategies=(signal("trend_following", 0.80), signal("momentum", 0.90), signal("breakout", 0.70)), active_strategy_count=3)
    result = select_strategy(portfolio, make_mtf())

    assert result.decision == "STRATEGY_SELECTED"
    assert result.selected_strategy_id == "momentum"
    assert result.selected_direction is SignalDirection.LONG
    assert all(item.status is QualificationStatus.QUALIFIED for item in result.qualifications)


def test_conflicting_mtf_bias_rejects_directional_strategy() -> None:
    from app.models.strategy import StrategyPortfolioResult

    portfolio = StrategyPortfolioResult(symbol="BTC/USD", timeframe="15m", source="test", generated_at=NOW, regime="STRONG_TREND_UP", regime_confidence=0.9, strategies=(signal("momentum", 0.95),), active_strategy_count=1)
    result = select_strategy(portfolio, make_mtf(bias=MTFBias.BEARISH, alignment=4, confirmation=False))

    assert result.decision == "NO_QUALIFIED_STRATEGY"
    assert result.selected_strategy_id is None
    assert result.qualifications[0].status is QualificationStatus.REJECTED
    assert result.qualifications[0].mtf_gate_passed is False


def test_alignment_below_three_fails_gate() -> None:
    from app.models.strategy import StrategyPortfolioResult

    portfolio = StrategyPortfolioResult(symbol="BTC/USD", timeframe="15m", source="test", generated_at=NOW, regime="STRONG_TREND_UP", regime_confidence=0.9, strategies=(signal("momentum", 0.95),), active_strategy_count=1)
    result = select_strategy(portfolio, make_mtf(alignment=2, confirmation=False))

    assert result.qualifications[0].status is QualificationStatus.REJECTED
    assert result.qualifications[0].mtf_alignment_count == 2
