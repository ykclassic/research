from __future__ import annotations

from datetime import timedelta

from app.models.market import OHLCVDataset


def validate_ohlcv_dataset(
    dataset: OHLCVDataset,
    *,
    require_contiguous: bool = False,
) -> OHLCVDataset:
    """Validate a canonical OHLCV dataset before research calculations consume it."""
    candles = dataset.candles
    if not candles:
        raise ValueError("OHLCV dataset must contain at least one candle.")

    for previous, current in zip(candles, candles[1:]):
        if current.timestamp <= previous.timestamp:
            raise ValueError("OHLCV candle timestamps must be strictly increasing.")
        if require_contiguous:
            expected = previous.timestamp + timedelta(seconds=dataset.timeframe.seconds)
            if current.timestamp != expected:
                raise ValueError(
                    "OHLCV dataset contains a timestamp gap for "
                    f"{dataset.symbol} {dataset.timeframe.value}."
                )

    return dataset
