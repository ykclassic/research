from datetime import datetime, timezone

import pytest

from app.models.news import EventType, NewsItem, SentimentLabel
from app.services.news_research import NewsResearchService


def test_news_item_preserves_provider_publication_timestamp_and_source():
    service = NewsResearchService()
    item = service._news_item(
        {
            "id": 123,
            "headline": "NVDA beats earnings expectations after strong growth",
            "summary": "Revenue increased and management raised guidance.",
            "source": "Example Wire",
            "url": "https://example.com/nvda",
            "datetime": 1788692400,
            "related": "NVDA",
            "category": "company",
        },
        "NVDA",
    )
    assert item is not None
    assert item.source == "Example Wire"
    assert item.source_url == "https://example.com/nvda"
    assert item.published_at.tzinfo == timezone.utc
    assert item.affected_assets == ("NVDA",)
    assert item.sentiment == SentimentLabel.POSITIVE
    assert item.event_type == EventType.EARNINGS


def test_event_classification_prioritizes_regulatory_and_macro_signals():
    service = NewsResearchService()
    assert service._event_type("SEC investigation into company compliance") == EventType.REGULATORY
    assert service._event_type("Federal Reserve interest rate decision") == EventType.MACRO
    assert service._event_type("Quarterly EPS and revenue results") == EventType.EARNINGS


def test_reaction_calculation_uses_prices_before_and_after_publication():
    from app.models.market import Candle, OHLCVDataset, Timeframe

    service = NewsResearchService()
    base = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=base,
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
            symbol="NVDA",
            timeframe=Timeframe.MINUTE_5,
            source="finnhub",
            is_complete=True,
        )
        for _ in []
    )
    rows = []
    for index, close in enumerate((100, 101, 102, 103)):
        timestamp = base.replace(minute=base.minute + index * 5)
        rows.append(Candle(
            timestamp=timestamp,
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1,
            symbol="NVDA",
            timeframe=Timeframe.MINUTE_5,
            source="finnhub",
            is_complete=True,
        ))
    dataset = OHLCVDataset(
        symbol="NVDA",
        timeframe=Timeframe.MINUTE_5,
        source="finnhub",
        requested_at=base,
        provider_timestamp=rows[-1].timestamp,
        candles=tuple(rows),
    )
    reaction = service._reaction(dataset, base + timedelta(minutes=5))
    assert reaction.baseline_price == 101
    assert reaction.reaction_price == 103
    assert reaction.direction == "UP"
    assert reaction.percent_change == pytest.approx((103 - 101) / 101 * 100)
