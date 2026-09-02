from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.models.market import OHLCVDataset, TechnicalAnalysisResult
from app.models.regime import MarketRegime, MarketRegimeResult
from app.models.strategy import (
    SignalDirection,
    StrategyDefinition,
    StrategyPortfolioResult,
    StrategySignal,
    StrategyStatus,
)


class Strategy(ABC):
    """Pure strategy contract: no provider, cache, database, or execution I/O."""

    definition: StrategyDefinition

    @abstractmethod
    def evaluate(
        self,
        dataset: OHLCVDataset,
        features: TechnicalAnalysisResult,
        regime: MarketRegimeResult,
    ) -> StrategySignal:
        raise NotImplementedError


def _finite_indicator(features: TechnicalAnalysisResult, name: str) -> float | None:
    value = features.indicators.get(name)
    return value if isinstance(value, (int, float)) else None


def _base_signal(
    strategy: StrategyDefinition,
    dataset: OHLCVDataset,
    regime: MarketRegimeResult,
    direction: SignalDirection,
    confidence: float,
    status: StrategyStatus,
    compatible: bool,
    rationale: str,
    indicators: tuple[str, ...],
    rules: tuple[str, ...],
) -> StrategySignal:
    return StrategySignal(
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.version,
        symbol=dataset.symbol,
        timeframe=dataset.timeframe,
        generated_at=datetime.now(timezone.utc),
        source=dataset.source,
        direction=direction,
        confidence=max(0.0, min(1.0, confidence)),
        status=status,
        regime=regime.regime,
        regime_compatible=compatible,
        rationale=rationale,
        indicators_used=indicators,
        rule_ids=rules,
    )


class TrendFollowingStrategy(Strategy):
    definition = StrategyDefinition(
        strategy_id="trend_following",
        version="1.0.0",
        name="EMA/ADX Trend Following",
        description="Follows aligned EMA structure only when ADX confirms a strong trend.",
        supported_timeframes=(
            "5m", "15m", "30m", "1h", "4h", "1d"
        ),
        supported_regimes=(MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN),
    )

    def evaluate(self, dataset, features, regime):
        values = {name: _finite_indicator(features, name) for name in ("ema20", "ema50", "ema200", "adx14")}
        if any(value is None for value in values.values()):
            return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.INSUFFICIENT_DATA, False, "Required EMA/ADX indicators are unavailable.", tuple(values), ("TF0",))

        bullish = dataset.latest_completed_candle.close > values["ema20"] > values["ema50"] > values["ema200"] and regime.regime is MarketRegime.STRONG_TREND_UP
        bearish = dataset.latest_completed_candle.close < values["ema20"] < values["ema50"] < values["ema200"] and regime.regime is MarketRegime.STRONG_TREND_DOWN
        compatible = regime.regime in self.definition.supported_regimes
        if bullish or bearish:
            direction = SignalDirection.LONG if bullish else SignalDirection.SHORT
            confidence = min(1.0, 0.55 + max(0.0, values["adx14"] - 25.0) / 50.0 + regime.confidence * 0.20)
            return _base_signal(self.definition, dataset, regime, direction, confidence, StrategyStatus.ACTIVE, True, "Price and EMA20/50/200 are aligned with the detected strong-trend regime and ADX confirmation.", tuple(values), ("TF1",))
        return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.ACTIVE, compatible, "Trend-following entry conditions are not satisfied on the latest completed candle.", tuple(values), ("TF2",))


class MeanReversionStrategy(Strategy):
    definition = StrategyDefinition(
        strategy_id="mean_reversion",
        version="1.0.0",
        name="RSI/Bollinger Mean Reversion",
        description="Looks for extreme RSI readings at the outer Bollinger bands in non-trending regimes.",
        supported_timeframes=("15m", "30m", "1h", "4h", "1d"),
        supported_regimes=(MarketRegime.RANGE, MarketRegime.LOW_VOLATILITY),
    )

    def evaluate(self, dataset, features, regime):
        names = ("rsi14", "bb_lower", "bb_upper", "bb_width")
        values = {name: _finite_indicator(features, name) for name in names}
        if any(value is None for value in values.values()):
            return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.INSUFFICIENT_DATA, False, "Required RSI/Bollinger indicators are unavailable.", names, ("MR0",))

        close = dataset.latest_completed_candle.close
        compatible = regime.regime in self.definition.supported_regimes
        long_setup = compatible and values["rsi14"] <= 30.0 and close <= values["bb_lower"]
        short_setup = compatible and values["rsi14"] >= 70.0 and close >= values["bb_upper"]
        if long_setup or short_setup:
            direction = SignalDirection.LONG if long_setup else SignalDirection.SHORT
            rsi_distance = abs(values["rsi14"] - 50.0) / 50.0
            confidence = min(1.0, 0.55 + rsi_distance * 0.25 + regime.confidence * 0.20)
            return _base_signal(self.definition, dataset, regime, direction, confidence, StrategyStatus.ACTIVE, True, "RSI is at an extreme and price is beyond the corresponding Bollinger boundary in a compatible regime.", names, ("MR1",))
        return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.ACTIVE, compatible, "Mean-reversion entry conditions are not satisfied on the latest completed candle.", names, ("MR2",))


class MomentumStrategy(Strategy):
    definition = StrategyDefinition(
        strategy_id="momentum",
        version="1.0.0",
        name="MACD Momentum",
        description="Uses MACD histogram direction with price/EMA confirmation and avoids strong counter-regime entries.",
        supported_timeframes=("5m", "15m", "30m", "1h", "4h", "1d"),
        supported_regimes=(MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN, MarketRegime.WEAK_TREND),
    )

    def evaluate(self, dataset, features, regime):
        names = ("macd", "macd_signal", "macd_histogram", "ema20")
        values = {name: _finite_indicator(features, name) for name in names}
        if any(value is None for value in values.values()):
            return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.INSUFFICIENT_DATA, False, "Required MACD/EMA indicators are unavailable.", names, ("MO0",))

        close = dataset.latest_completed_candle.close
        compatible = regime.regime in self.definition.supported_regimes
        long_setup = compatible and values["macd"] > values["macd_signal"] and values["macd_histogram"] > 0 and close > values["ema20"]
        short_setup = compatible and values["macd"] < values["macd_signal"] and values["macd_histogram"] < 0 and close < values["ema20"]
        if long_setup or short_setup:
            direction = SignalDirection.LONG if long_setup else SignalDirection.SHORT
            confidence = min(1.0, 0.50 + min(0.30, abs(values["macd_histogram"]) / max(abs(close), 1e-12) * 100.0) + regime.confidence * 0.20)
            return _base_signal(self.definition, dataset, regime, direction, confidence, StrategyStatus.ACTIVE, True, "MACD line and histogram agree with price position relative to EMA20 in a compatible regime.", names, ("MO1",))
        return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.ACTIVE, compatible, "Momentum entry conditions are not satisfied on the latest completed candle.", names, ("MO2",))


class BreakoutStrategy(Strategy):
    definition = StrategyDefinition(
        strategy_id="breakout",
        version="1.0.0",
        name="Donchian Breakout",
        description="Detects a close outside the previous completed 20-candle range with volatility confirmation.",
        supported_timeframes=("5m", "15m", "30m", "1h", "4h", "1d"),
        supported_regimes=(MarketRegime.STRONG_TREND_UP, MarketRegime.STRONG_TREND_DOWN, MarketRegime.HIGH_VOLATILITY),
    )
    lookback = 20

    def evaluate(self, dataset, features, regime):
        completed = list(dataset.completed_candles)
        if len(completed) <= self.lookback:
            return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.INSUFFICIENT_DATA, False, f"At least {self.lookback + 1} completed candles are required for breakout evaluation.", (), ("BO0",))

        previous = completed[-self.lookback - 1 : -1]
        current = completed[-1]
        prior_high = max(c.high for c in previous)
        prior_low = min(c.low for c in previous)
        atr = _finite_indicator(features, "atr14")
        compatible = regime.regime in self.definition.supported_regimes
        long_setup = compatible and current.close > prior_high
        short_setup = compatible and current.close < prior_low
        if long_setup or short_setup:
            direction = SignalDirection.LONG if long_setup else SignalDirection.SHORT
            range_size = max(prior_high - prior_low, 1e-12)
            extension = abs(current.close - (prior_high if long_setup else prior_low)) / range_size
            volatility_bonus = min(0.15, (atr / current.close) if atr else 0.0)
            confidence = min(1.0, 0.60 + min(0.25, extension) + volatility_bonus + regime.confidence * 0.10)
            return _base_signal(self.definition, dataset, regime, direction, confidence, StrategyStatus.ACTIVE, True, "The latest completed candle closed beyond the previous 20-candle high/low in a compatible regime.", ("atr14",), ("BO1",))
        return _base_signal(self.definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.ACTIVE, compatible, "No breakout beyond the previous 20 completed candles was confirmed.", ("atr14",), ("BO2",))


class StrategyPortfolio:
    """Evaluate every registered strategy independently.

    The portfolio is intentionally an evaluation layer, not a selector. It
    never combines signals, assigns capital, or executes trades.
    """

    def __init__(self, strategies: tuple[Strategy, ...] | None = None) -> None:
        self._strategies = strategies or (
            TrendFollowingStrategy(),
            MeanReversionStrategy(),
            MomentumStrategy(),
            BreakoutStrategy(),
        )
        ids = [strategy.definition.strategy_id for strategy in self._strategies]
        if len(ids) != len(set(ids)):
            raise ValueError("Strategy IDs must be unique.")

    @property
    def definitions(self) -> tuple[StrategyDefinition, ...]:
        return tuple(strategy.definition for strategy in self._strategies)

    def evaluate(self, dataset: OHLCVDataset, features: TechnicalAnalysisResult, regime: MarketRegimeResult) -> StrategyPortfolioResult:
        if dataset.symbol != features.symbol or dataset.symbol != regime.symbol:
            raise ValueError("Dataset, feature, and regime symbols must match.")
        if dataset.timeframe != features.timeframe or dataset.timeframe != regime.timeframe:
            raise ValueError("Dataset, feature, and regime timeframes must match.")
        if dataset.source != features.source or dataset.source != regime.source:
            raise ValueError("Dataset, feature, and regime sources must match.")
        if not dataset.latest_candle.is_complete:
            raise ValueError("Strategy evaluation requires a completed latest candle.")
        if features.latest_candle_timestamp != dataset.latest_candle.timestamp:
            raise ValueError("Features must be calculated from the same latest completed candle as the dataset.")
        if regime.latest_candle_timestamp != dataset.latest_candle.timestamp:
            raise ValueError("Regime must be calculated from the same latest completed candle as the dataset.")

        signals: list[StrategySignal] = []
        for strategy in self._strategies:
            definition = strategy.definition
            if not definition.enabled or dataset.timeframe not in definition.supported_timeframes:
                signals.append(_base_signal(definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.DISABLED, False, "Strategy is disabled or does not support this timeframe.", (), ("PORTFOLIO_DISABLED",)))
                continue
            try:
                signals.append(strategy.evaluate(dataset, features, regime))
            except (ValueError, TypeError, KeyError) as exc:
                signals.append(_base_signal(definition, dataset, regime, SignalDirection.NEUTRAL, 0.0, StrategyStatus.ERROR, False, f"Strategy evaluation failed deterministically: {exc}", (), ("PORTFOLIO_ERROR",)))

        return StrategyPortfolioResult(
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            source=dataset.source,
            generated_at=datetime.now(timezone.utc),
            regime=regime.regime,
            regime_confidence=regime.confidence,
            strategies=tuple(signals),
            active_strategy_count=sum(signal.status is StrategyStatus.ACTIVE for signal in signals),
        )


_default_portfolio = StrategyPortfolio()


def evaluate_strategy_portfolio(dataset: OHLCVDataset, features: TechnicalAnalysisResult, regime: MarketRegimeResult) -> StrategyPortfolioResult:
    """Evaluate the canonical Phase 6 strategy portfolio."""
    return _default_portfolio.evaluate(dataset, features, regime)
