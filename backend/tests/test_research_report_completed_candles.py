from datetime import datetime, timedelta, timezone

from app.models.market import Candle, OHLCVDataset, Timeframe
from app.services.research_report import ResearchReportService


def test_completed_dataset_removes_forming_latest_candle():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(days=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0,
            symbol="GBP/USD",
            timeframe=Timeframe.DAY_1,
            source="test",
            is_complete=index < 3,
        )
        for index in range(4)
    )
    dataset = OHLCVDataset(
        symbol="GBP/USD",
        timeframe=Timeframe.DAY_1,
        source="test",
        requested_at=start,
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
    )

    completed = ResearchReportService._completed_dataset(dataset)

    assert len(completed.candles) == 3
    assert all(candle.is_complete for candle in completed.candles)
    assert completed.latest_candle.timestamp == candles[-2].timestamp
