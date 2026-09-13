from unittest.mock import AsyncMock

import pytest

from app.models.market import Timeframe
from app.services.news_research_resilient import ResilientNewsResearchService
from app.services.research_report import ResearchReportService


@pytest.mark.asyncio
async def test_crypto_report_prefers_kraken_public_candles():
    service = ResearchReportService()
    expected = object()
    service.kraken_public.get_candles = AsyncMock(return_value=expected)
    service.quote_service.orchestrator.get_candles = AsyncMock()

    result = await service._dataset("ETH/USD", Timeframe.HOUR_1, 300)

    assert result is expected
    service.kraken_public.get_candles.assert_awaited_once_with("ETH/USD", Timeframe.HOUR_1, 300)
    service.quote_service.orchestrator.get_candles.assert_not_awaited()


@pytest.mark.asyncio
async def test_crypto_report_falls_back_to_orchestrator_when_kraken_fails():
    service = ResearchReportService()
    expected = object()
    service.kraken_public.get_candles = AsyncMock(side_effect=RuntimeError("Kraken unavailable"))
    service.quote_service.orchestrator.get_candles = AsyncMock(return_value=expected)

    result = await service._dataset("ETH/USD", Timeframe.HOUR_1, 300)

    assert result is expected
    service.quote_service.orchestrator.get_candles.assert_awaited_once_with("ETH/USD", Timeframe.HOUR_1, 300)


def test_research_report_uses_resilient_news_service():
    service = ResearchReportService()

    assert isinstance(service.news_service, ResilientNewsResearchService)
