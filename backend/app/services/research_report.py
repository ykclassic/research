from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models.market import OHLCVDataset, Timeframe
from app.models.research_report import FundamentalContext, MarketStatus, ReportTimeframe, ResearchReport, SMCStructure
from app.providers.kraken_public import KrakenPublicProvider
from app.services.feature_engine import calculate_feature_set
from app.services.market_structure import analyze_market_structure
from app.services.news_research_resilient import ResilientNewsResearchService
from app.services.regime_detection import detect_regime
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol

REPORT_TIMEFRAMES = (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15)
MIN_REPORT_CANDLES = 220


class ResearchReportService:
    def __init__(self) -> None:
        self.quote_service = QuoteService()
        # Crypto reports use Kraken's credential-free public market data first.
        # The paid-provider orchestrator remains the secondary fallback.
        self.kraken_public = KrakenPublicProvider()
        # News is enrichment, not a hard dependency for deterministic reports.
        # Use the resilient service so one failed Finnhub feed cannot abort the
        # entire research report.
        self.news_service = ResilientNewsResearchService()

    async def _dataset(self, symbol: str, timeframe: Timeframe, limit: int = 300):
        mapping = normalize_symbol(symbol)
        timeout = max(settings.analysis_timeout_seconds, settings.provider_timeout_seconds * 7)

        if mapping.asset_class == "crypto":
            try:
                # Kraken provides the exact report hierarchy without consuming
                # Twelve Data/Finnhub/Alpha Vantage candle quota.
                return await asyncio.wait_for(
                    self.kraken_public.get_candles(mapping.internal, timeframe, limit),
                    timeout=settings.analysis_timeout_seconds,
                )
            except Exception as primary_error:
                # Preserve the existing multi-provider orchestrator as a true
                # secondary path if Kraken is temporarily unavailable.
                try:
                    return await asyncio.wait_for(
                        self.quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit),
                        timeout=timeout,
                    )
                except Exception as fallback_error:
                    raise RuntimeError(
                        f"Crypto candle acquisition failed for {mapping.internal} {timeframe.value}: "
                        f"primary={primary_error}; fallback={fallback_error}"
                    ) from fallback_error

        return await asyncio.wait_for(
            self.quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit),
            timeout=timeout,
        )

    async def _current_quote(self, symbol: str):
        mapping = normalize_symbol(symbol)
        if mapping.asset_class == "crypto":
            try:
                # The report must have a genuinely current crypto price even
                # when the quota-limited provider pool is exhausted.
                return await asyncio.wait_for(
                    self.kraken_public.get_quote(mapping.internal),
                    timeout=settings.analysis_timeout_seconds,
                )
            except Exception as primary_error:
                try:
                    return await self.quote_service.get_quote(mapping.internal, force_refresh=True)
                except Exception as fallback_error:
                    raise RuntimeError(
                        f"Current crypto quote acquisition failed for {mapping.internal}: "
                        f"primary={primary_error}; fallback={fallback_error}"
                    ) from fallback_error
        return await self.quote_service.get_quote(mapping.internal, force_refresh=True)

    @staticmethod
    def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
        """Create the research snapshot from completed candles only.

        Providers may legitimately return the currently-forming candle. Research
        reports must never pass that candle into regime detection or other
        deterministic research calculations that require closed bars.
        """
        completed = dataset.completed_candles
        if not completed:
            raise ValueError(f"No completed candles are available for {dataset.symbol} {dataset.timeframe.value}.")
        return dataset.model_copy(update={"candles": completed})

    @staticmethod
    def _support_resistance(candles) -> tuple[float | None, float | None]:
        completed = list(candles.completed_candles)
        if len(completed) < 5:
            return None, None
        window = completed[-50:]
        current = completed[-1].close
        supports = [c.low for c in window if c.low <= current]
        resistances = [c.high for c in window if c.high >= current]
        return (
            max(supports) if supports else min(c.low for c in window),
            min(resistances) if resistances else max(c.high for c in window),
        )

    @staticmethod
    def _momentum(indicators: dict) -> str:
        rsi, macd = indicators.get("rsi14"), indicators.get("macd_histogram")
        if isinstance(rsi, float) and isinstance(macd, float):
            if rsi >= 60 and macd > 0:
                return "BULLISH"
            if rsi <= 40 and macd < 0:
                return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _structure_label(events) -> str:
        recent = list(events)[-12:]
        if any(e.type in {"BOS_BULLISH", "CHOCH_BULLISH"} for e in recent):
            return "BULLISH_BREAK"
        if any(e.type in {"BOS_BEARISH", "CHOCH_BEARISH"} for e in recent):
            return "BEARISH_BREAK"
        return "RANGE_STRUCTURE"

    @staticmethod
    def _smc(events) -> SMCStructure:
        recent = list(events)[-20:]
        bos = next((e.type for e in reversed(recent) if e.type.startswith("BOS_")), None)
        return SMCStructure(
            bos=bos,
            fvg=[f"{e.type} @ {e.price:.6g}" for e in recent if e.type.startswith("FVG_")][-3:],
            order_blocks=[f"{e.type} @ {e.price:.6g}" for e in recent if e.type.startswith("ORDER_BLOCK_")][-3:],
            liquidity=[f"{e.type} @ {e.price:.6g}" for e in recent if "LIQUIDITY" in e.type or "STOP_RUN" in e.type][-4:],
        )

    @staticmethod
    def _change_24h(h1_dataset, current: float) -> float | None:
        completed = list(h1_dataset.completed_candles)
        if not completed or current <= 0:
            return None
        target = completed[-1].timestamp - timedelta(hours=24)
        baseline = min(completed, key=lambda candle: abs((candle.timestamp - target).total_seconds()))
        if baseline.close <= 0:
            return None
        return (current - baseline.close) / baseline.close * 100

    @staticmethod
    def _score(status: MarketStatus, mtf: list[ReportTimeframe], fundamental: FundamentalContext) -> tuple[int, dict[str, float]]:
        trend_score = 85.0 if status.trend == "BULLISH" else 15.0 if status.trend == "BEARISH" else 50.0
        momentum_score = 85.0 if status.momentum == "BULLISH" else 15.0 if status.momentum == "BEARISH" else 50.0
        regime_score = 70.0 if "UP" in status.market_regime else 30.0 if "DOWN" in status.market_regime else 50.0
        mtf_bull = sum(item.trend == "BULLISH" for item in mtf)
        mtf_bear = sum(item.trend == "BEARISH" for item in mtf)
        mtf_score = 50.0 + 40.0 * ((mtf_bull - mtf_bear) / max(1, len(mtf)))
        components = {
            "trend": trend_score,
            "momentum": momentum_score,
            "regime": regime_score,
            "multi_timeframe": mtf_score,
            "fundamental": 50.0,
        }
        return max(0, min(100, round(sum(components.values()) / len(components)))), components

    async def generate(self, symbol: str) -> ResearchReport:
        symbol = normalize_symbol(symbol).internal
        raw_datasets = await asyncio.gather(*(self._dataset(symbol, tf, 300) for tf in REPORT_TIMEFRAMES))
        # The provider response can contain a still-forming latest candle. Build
        # the report from a completed-candle snapshot so every deterministic
        # calculation observes the same closed-bar contract as regime detection.
        datasets = [self._completed_dataset(dataset) for dataset in raw_datasets]
        current_quote = await self._current_quote(symbol)
        if current_quote.price is None:
            raise RuntimeError("Current quote is unavailable; report cannot present a current price.")

        daily, h1 = datasets[0], datasets[2]
        if len(daily.completed_candles) < MIN_REPORT_CANDLES:
            raise ValueError(f"At least {MIN_REPORT_CANDLES} completed candles are required for the research report.")

        daily_features = calculate_feature_set(daily)
        daily_structure = analyze_market_structure(daily)
        regime = detect_regime(daily)
        support, resistance = self._support_resistance(daily)
        momentum = self._momentum(daily_features.indicators)
        trend = str(daily_features.indicators.get("trend") or "UNKNOWN")
        status = MarketStatus(
            current_price=current_quote.price,
            change_24h_percent=self._change_24h(h1, current_quote.price),
            volume=(
                getattr(current_quote, "volume", None)
                if getattr(current_quote, "volume", None) is not None
                else daily.completed_candles[-1].volume
            ),
            volatility_percent=(
                daily_features.indicators.get("atr14") / current_quote.price * 100
                if isinstance(daily_features.indicators.get("atr14"), float)
                else None
            ),
            technical_structure=self._structure_label(daily_structure.events),
            trend=trend,
            momentum=momentum,
            support=support,
            resistance=resistance,
            market_regime=regime.regime.value,
        )

        mtf: list[ReportTimeframe] = []
        for dataset in datasets:
            features = calculate_feature_set(dataset)
            structure = analyze_market_structure(dataset)
            tf_regime = detect_regime(dataset) if len(dataset.completed_candles) >= MIN_REPORT_CANDLES else None
            tf_support, tf_resistance = self._support_resistance(dataset)
            mtf.append(
                ReportTimeframe(
                    timeframe=dataset.timeframe.value,
                    trend=str(features.indicators.get("trend") or "UNKNOWN"),
                    momentum=self._momentum(features.indicators),
                    support=tf_support,
                    resistance=tf_resistance,
                    regime=tf_regime.regime.value if tf_regime else "UNKNOWN",
                    latest_candle_timestamp=dataset.latest_completed_candle.timestamp,
                )
            )
            _ = structure

        try:
            news = await self.news_service.research(symbol=symbol, days=1, limit=12)
            fundamental = FundamentalContext(
                news_count=len(news.news),
                macro_count=sum(e.event_type.value == "MACRO" for e in news.fundamental_events),
                event_count=len(news.fundamental_events),
                headlines=[item.headline for item in news.news[:5]],
            )
        except (RuntimeError, ValueError, asyncio.TimeoutError):
            # Fundamental/news context is enrichment. Market-data-backed report
            # generation must remain available when the news provider is degraded.
            fundamental = FundamentalContext()

        score, basis = self._score(status, mtf, fundamental)
        bull = [
            f"Daily trend is {status.trend.lower()}.",
            f"Market regime is {status.market_regime}.",
            f"{sum(x.trend == 'BULLISH' for x in mtf)}/{len(mtf)} timeframes are bullish.",
        ]
        bear = [
            f"Daily momentum is {status.momentum.lower()}.",
            f"Resistance is near {resistance:.6g}." if resistance else "Resistance is unavailable.",
            "A regime transition or structural break would weaken the thesis.",
        ]
        risks = [
            "News and macro events can invalidate technical structure rapidly.",
            "Provider freshness or incomplete candles can reduce report confidence.",
            "The research score is deterministic and is not a probability of profit.",
        ]
        invalidation = [
            f"Bull thesis invalidation: sustained price below support {support:.6g}."
            if support
            else "Bull thesis invalidation: loss of the latest validated support.",
            "Bear thesis invalidation: confirmed bullish structure break above resistance.",
        ]
        interpretation = (
            f"{symbol} currently has a {status.trend.lower()} technical trend, "
            f"{status.momentum.lower()} momentum, and a {status.market_regime} regime. "
            "The report combines deterministic market structure, multi-timeframe evidence, "
            "and available fundamental context; it does not infer causation from headlines."
        )
        return ResearchReport(
            symbol=symbol,
            generated_at=datetime.now(timezone.utc),
            market_status=status,
            indicators=daily_features.indicators,
            regime_snapshot=regime.model_dump(mode="json"),
            smc_structure=self._smc(daily_structure.events),
            multi_timeframe=mtf,
            fundamental_context=fundamental,
            ai_interpretation=interpretation,
            bull_case=bull,
            bear_case=bear,
            key_risks=risks,
            invalidation=invalidation,
            overall_research_score=score,
            score_basis=basis,
        )
