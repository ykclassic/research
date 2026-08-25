from __future__ import annotations

from datetime import datetime, timezone

from app.models.market import OHLCVDataset, TechnicalAnalysisResult
from app.services.technical_analysis import calculate_indicators


MINIMUM_CANDLES = 20


class FeatureEngine:
    """Canonical deterministic feature-engine entry point.

    The engine owns dataset preparation and delegates the pure numerical
    indicator calculations to the existing technical-analysis implementation.
    No provider access or network I/O is permitted here.
    """

    def __init__(self, minimum_candles: int = MINIMUM_CANDLES) -> None:
        if minimum_candles < 1:
            raise ValueError("minimum_candles must be greater than zero")
        self.minimum_candles = minimum_candles

    def calculate(self, dataset: OHLCVDataset) -> TechnicalAnalysisResult:
        completed = dataset.completed_candles
        if len(completed) < self.minimum_candles:
            raise ValueError(
                f"At least {self.minimum_candles} completed candles are required."
            )

        # A forming candle is allowed at the end of a provider dataset, but it
        # must never enter the deterministic feature calculation.
        if any(not candle.is_complete for candle in dataset.candles[:-1]):
            raise ValueError(
                "Incomplete candles may only occur at the end of an OHLCV dataset."
            )

        indicators = calculate_indicators(list(completed))
        latest = completed[-1]

        return TechnicalAnalysisResult(
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            source=dataset.source,
            calculated_at=datetime.now(timezone.utc),
            latest_candle_timestamp=latest.timestamp,
            candle_count=len(completed),
            indicators=indicators,
        )


_default_engine = FeatureEngine()


def calculate_feature_set(dataset: OHLCVDataset) -> TechnicalAnalysisResult:
    """Calculate the canonical deterministic feature set."""
    return _default_engine.calculate(dataset)
