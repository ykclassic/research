from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.news import EventType, FundamentalEvent, NewsItem, SentimentLabel
from app.services.news_research_resilient import ResilientNewsResearchService


@pytest.mark.asyncio
async def test_gather_keeps_healthy_feeds_when_economic_calendar_fails(monkeypatch):
    service = ResilientNewsResearchService()
    published = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    news = NewsItem(
        id="news-1",
        headline="Markets gain on strong outlook",
        summary="",
        source="Test Source",
        source_url="https://example.com/news-1",
        published_at=published,
        related_entities=("AAPL",),
        affected_assets=("AAPL",),
        event_type=EventType.NEWS,
        sentiment=SentimentLabel.POSITIVE,
        sentiment_score=1.0,
    )
    earnings = FundamentalEvent(
        id="earnings:AAPL:2026-09-06:3:2026",
        event_type=EventType.EARNINGS,
        title="AAPL earnings",
        description="Test earnings event",
        event_timestamp=published,
        affected_assets=("AAPL",),
    )

    async def fake_news(*args, **kwargs):
        return [news]

    async def fake_earnings(*args, **kwargs):
        return [earnings]

    async def failing_economic(*args, **kwargs):
        raise RuntimeError("provider failure containing sensitive request details")

    monkeypatch.setattr(service, "_fetch_news", fake_news)
    monkeypatch.setattr(service, "_fetch_earnings", fake_earnings)
    monkeypatch.setattr(service, "_fetch_economic", failing_economic)

    result = await service._gather("AAPL", published, published)

    assert result[0] == [news]
    assert result[1] == [earnings]
    assert result[2] == []


@pytest.mark.asyncio
async def test_research_returns_partial_response_when_one_feed_fails(monkeypatch):
    service = ResilientNewsResearchService()

    async def fake_gather(*args, **kwargs):
        return [], [], []

    monkeypatch.setattr(service, "_gather", fake_gather)
    monkeypatch.setattr(service, "_correlate", lambda news: [])

    result = await service.research(days=1, limit=25)

    assert result.news == ()
    assert result.fundamental_events == ()
    assert result.coverage["news"] == 0
