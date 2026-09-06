from datetime import datetime, timezone

from app.models.research_report import FundamentalContext, MarketStatus, ReportTimeframe, ResearchReport, SMCStructure
from app.services.research_report import ResearchReportService


def _status(trend="BULLISH", momentum="BULLISH", regime="STRONG_TREND_UP"):
    return MarketStatus(current_price=100.0, change_24h_percent=2.0, volume=1000.0, volatility_percent=1.5, technical_structure="BULLISH_BREAK", trend=trend, momentum=momentum, support=95.0, resistance=110.0, market_regime=regime)


def test_report_score_is_bounded_and_deterministic():
    mtf = [ReportTimeframe(timeframe=tf, trend="BULLISH", momentum="BULLISH", support=95.0, resistance=110.0, regime="STRONG_TREND_UP", latest_candle_timestamp=datetime.now(timezone.utc)) for tf in ("1d", "4h", "1h", "15m")]
    score, basis = ResearchReportService._score(_status(), mtf, FundamentalContext(news_count=4))
    assert score == 76
    assert 0 <= score <= 100
    assert set(basis) == {"trend", "momentum", "regime", "multi_timeframe", "fundamental"}


def test_report_contract_contains_requested_sections():
    report = ResearchReport(symbol="BTC/USD", generated_at=datetime.now(timezone.utc), market_status=_status(), smc_structure=SMCStructure(bos="BOS_BULLISH", fvg=["FVG_BULLISH @ 101"], order_blocks=["ORDER_BLOCK_BULLISH @ 99"], liquidity=["LIQUIDITY_POOL_HIGH @ 110"]), multi_timeframe=[], fundamental_context=FundamentalContext(news_count=2), ai_interpretation="evidence", bull_case=["trend"], bear_case=["risk"], key_risks=["volatility"], invalidation=["support loss"], overall_research_score=84)
    assert report.symbol == "BTC/USD"
    assert report.smc_structure.bos == "BOS_BULLISH"
    assert report.overall_research_score == 84
