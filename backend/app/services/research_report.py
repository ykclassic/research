from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import OHLCVDataset, Timeframe
from app.models.research_report import FundamentalContext, MarketStatus, ReportTimeframe, ResearchReport, ResearchRequestConfiguration, SMCStructure
from app.providers.kraken_public import KrakenPublicProvider
from app.services.feature_engine import calculate_feature_set
from app.services.market_structure import analyze_market_structure
from app.services.news_research_resilient import ResilientNewsResearchService
from app.services.regime_detection import detect_regime
from app.services.quote_service import QuoteService
from app.services.research_preferences import ResearchRequestConfiguration as ResolvedResearchConfiguration
from app.symbols import normalize_symbol

REPORT_TIMEFRAMES = (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15)
TIMEFRAME_BY_PREFERENCE = {"15m": Timeframe.MINUTE_15, "1h": Timeframe.HOUR_1, "4h": Timeframe.HOUR_4, "1D": Timeframe.DAY_1}
MIN_REPORT_CANDLES = 220


class ResearchReportService:
    def __init__(self) -> None:
        self.quote_service = QuoteService()
        self.kraken_public = KrakenPublicProvider()
        self.news_service = ResilientNewsResearchService()

    @staticmethod
    def _validate_quote_policy(quote: Quote, config: ResolvedResearchConfiguration) -> None:
        age = quote.freshness_age_seconds
        stale = age is not None and (quote.status == QuoteStatus.STALE or age > config.maximum_data_age_seconds)
        if config.reject_stale_data and stale:
            raise RuntimeError(f"Market quote for {quote.symbol} is stale ({age:.1f}s); maximum acceptable age is {config.maximum_data_age_seconds}s.")
        if not config.allow_cached_data_fallback and quote.cache_hit and quote.fallback_used:
            raise RuntimeError(f"Validated cache fallback is disabled for {quote.symbol}; live market data is required.")

    @staticmethod
    def _validate_dataset_policy(dataset: OHLCVDataset, config: ResolvedResearchConfiguration) -> None:
        if config.require_completed_candles and not dataset.completed_candles:
            raise RuntimeError(f"No completed candles are available for {dataset.symbol} {dataset.timeframe.value}.")
        age = dataset.freshness_age_seconds
        stale = age is not None and (dataset.freshness_status.value == "STALE" or age > config.maximum_data_age_seconds)
        if config.reject_stale_data and stale:
            raise RuntimeError(f"Market candles for {dataset.symbol} {dataset.timeframe.value} are stale ({age:.1f}s); maximum acceptable age is {config.maximum_data_age_seconds}s.")
        if not config.allow_cached_data_fallback and dataset.cache_hit and dataset.fallback_used:
            raise RuntimeError(f"Validated cache fallback is disabled for {dataset.symbol} {dataset.timeframe.value}; live market data is required.")

    async def _dataset(self, symbol: str, timeframe: Timeframe, limit: int, config: ResolvedResearchConfiguration | None = None):
        mapping = normalize_symbol(symbol)
        if config is None:
            config = ResolvedResearchConfiguration(default_asset="BTC/USD", default_asset_class="Crypto", default_timeframe="1h", analysis_depth="Standard", technical_analysis_enabled=True, market_structure_enabled=True, multi_timeframe_enabled=True, fundamental_analysis_enabled=True, news_analysis_enabled=True, ai_interpretation_enabled=True)
            validate_policy = False
        else:
            validate_policy = True
        timeout = max(settings.analysis_timeout_seconds, settings.provider_timeout_seconds * 7)
        if mapping.asset_class == "crypto":
            try:
                dataset = await asyncio.wait_for(self.kraken_public.get_candles(mapping.internal, timeframe, limit), timeout=settings.analysis_timeout_seconds)
                if validate_policy:
                    self._validate_dataset_policy(dataset, config)
                return dataset
            except Exception as primary_error:
                try:
                    dataset = await asyncio.wait_for(self.quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit), timeout=timeout)
                    if validate_policy:
                        self._validate_dataset_policy(dataset, config)
                    return dataset
                except Exception as fallback_error:
                    raise RuntimeError(f"Crypto candle acquisition failed for {mapping.internal} {timeframe.value}: primary={primary_error}; fallback={fallback_error}") from fallback_error
        dataset = await asyncio.wait_for(self.quote_service.orchestrator.get_candles(mapping.internal, timeframe, limit), timeout=timeout)
        if validate_policy:
            self._validate_dataset_policy(dataset, config)
        return dataset

    async def _current_quote(self, symbol: str, config: ResolvedResearchConfiguration | None = None):
        if config is None:
            config = ResolvedResearchConfiguration(default_asset="BTC/USD", default_asset_class="Crypto", default_timeframe="1h", analysis_depth="Standard", technical_analysis_enabled=True, market_structure_enabled=True, multi_timeframe_enabled=True, fundamental_analysis_enabled=True, news_analysis_enabled=True, ai_interpretation_enabled=True)
            validate_policy = False
        else:
            validate_policy = True
        mapping = normalize_symbol(symbol)
        if mapping.asset_class == "crypto":
            try:
                quote = await asyncio.wait_for(self.kraken_public.get_quote(mapping.internal), timeout=settings.analysis_timeout_seconds)
                if validate_policy:
                    self._validate_quote_policy(quote, config)
                return quote
            except Exception as primary_error:
                try:
                    quote = await self.quote_service.get_quote(mapping.internal, force_refresh=True)
                    if validate_policy:
                        self._validate_quote_policy(quote, config)
                    return quote
                except Exception as fallback_error:
                    raise RuntimeError(f"Current crypto quote acquisition failed for {mapping.internal}: primary={primary_error}; fallback={fallback_error}") from fallback_error
        quote = await self.quote_service.get_quote(mapping.internal, force_refresh=True)
        if validate_policy:
            self._validate_quote_policy(quote, config)
        return quote

    @staticmethod
    def _completed_dataset(dataset: OHLCVDataset) -> OHLCVDataset:
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
        return (max(supports) if supports else min(c.low for c in window), min(resistances) if resistances else max(c.high for c in window))

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
    def _change_24h(dataset: OHLCVDataset, current: float) -> float | None:
        completed = list(dataset.completed_candles)
        if not completed or current <= 0:
            return None
        target = completed[-1].timestamp - timedelta(hours=24)
        baseline = min(completed, key=lambda candle: abs((candle.timestamp - target).total_seconds()))
        if baseline.close <= 0:
            return None
        return (current - baseline.close) / baseline.close * 100

    @staticmethod
    def _score(status: MarketStatus, mtf: list[ReportTimeframe], fundamental: FundamentalContext | None = None) -> tuple[int, dict[str, float]]:
        if status.trend == "NOT_REQUESTED":
            return 50, {"trend": 50.0, "momentum": 50.0, "regime": 50.0, "multi_timeframe": 50.0, "fundamental": 50.0}
        trend_score = 85.0 if status.trend == "BULLISH" else 15.0 if status.trend == "BEARISH" else 50.0
        momentum_score = 85.0 if status.momentum == "BULLISH" else 15.0 if status.momentum == "BEARISH" else 50.0
        regime_score = 70.0 if "UP" in status.market_regime else 30.0 if "DOWN" in status.market_regime else 50.0
        mtf_bull = sum(item.trend == "BULLISH" for item in mtf)
        mtf_bear = sum(item.trend == "BEARISH" for item in mtf)
        mtf_score = 50.0 + 40.0 * ((mtf_bull - mtf_bear) / max(1, len(mtf))) if mtf else 50.0
        components = {"trend": trend_score, "momentum": momentum_score, "regime": regime_score, "multi_timeframe": mtf_score, "fundamental": 50.0}
        return max(0, min(100, round(sum(components.values()) / len(components)))), components

    @staticmethod
    def _configuration_model(config: ResolvedResearchConfiguration) -> ResearchRequestConfiguration:
        return ResearchRequestConfiguration(
            default_asset=config.default_asset,
            default_asset_class=config.default_asset_class,
            default_timeframe=config.default_timeframe,
            analysis_depth=config.analysis_depth,
            **config.requested_components,
            maximum_data_age_seconds=config.maximum_data_age_seconds,
            reject_stale_data=config.reject_stale_data,
            require_completed_candles=config.require_completed_candles,
            allow_cached_data_fallback=config.allow_cached_data_fallback,
        )

    async def generate(self, symbol: str | None = None, configuration: ResolvedResearchConfiguration | None = None) -> ResearchReport:
        config = configuration or ResolvedResearchConfiguration(default_asset="BTC/USD", default_asset_class="Crypto", default_timeframe="1h", analysis_depth="Standard", technical_analysis_enabled=True, market_structure_enabled=True, multi_timeframe_enabled=True, fundamental_analysis_enabled=True, news_analysis_enabled=True, ai_interpretation_enabled=True)
        requested_symbol = config.default_asset if not symbol or not symbol.strip() else symbol
        symbol = normalize_symbol(requested_symbol).internal
        primary_timeframe = TIMEFRAME_BY_PREFERENCE[config.primary_timeframe()]
        required_timeframes: list[Timeframe] = []
        if config.technical_analysis_enabled or config.market_structure_enabled or config.multi_timeframe_enabled:
            if config.multi_timeframe_enabled:
                required_timeframes = list(REPORT_TIMEFRAMES)
                if primary_timeframe not in required_timeframes:
                    required_timeframes.append(primary_timeframe)
            else:
                required_timeframes = [primary_timeframe]
        raw_datasets = await asyncio.gather(*(self._dataset(symbol, timeframe, config.data_limit, config) for timeframe in required_timeframes))
        datasets = {dataset.timeframe: self._completed_dataset(dataset) for dataset in raw_datasets}
        current_quote = await self._current_quote(symbol, config)
        if current_quote.price is None:
            raise RuntimeError("Current quote is unavailable; report cannot present a current price.")
        primary = datasets.get(primary_timeframe)
        technical_indicators: dict[str, object] = {}
        regime_snapshot: dict[str, object] = {}
        structure_label = "NOT_REQUESTED"
        trend = "NOT_REQUESTED"
        momentum = "NOT_REQUESTED"
        support = None
        resistance = None
        primary_structure = None
        primary_regime = None
        if config.technical_analysis_enabled and primary is not None:
            if len(primary.completed_candles) < MIN_REPORT_CANDLES:
                raise ValueError(f"At least {MIN_REPORT_CANDLES} completed candles are required for technical research.")
            features = calculate_feature_set(primary)
            technical_indicators = features.indicators
            trend = str(features.indicators.get("trend") or "UNKNOWN")
            momentum = self._momentum(features.indicators)
            support, resistance = self._support_resistance(primary)
            primary_regime = detect_regime(primary)
            regime_snapshot = primary_regime.model_dump(mode="json")
        if config.market_structure_enabled and primary is not None:
            primary_structure = analyze_market_structure(primary)
            structure_label = self._structure_label(primary_structure.events)
            if not config.technical_analysis_enabled:
                support, resistance = self._support_resistance(primary)
        if config.technical_analysis_enabled and primary_regime is None and primary is not None:
            primary_regime = detect_regime(primary)
            regime_snapshot = primary_regime.model_dump(mode="json")
        market_regime = primary_regime.regime.value if primary_regime is not None else "NOT_REQUESTED"
        volatility = None
        if config.technical_analysis_enabled:
            atr = technical_indicators.get("atr14")
            if isinstance(atr, (int, float)) and current_quote.price > 0:
                volatility = float(atr) / current_quote.price * 100
        status_dataset = primary or next(iter(datasets.values()), None)
        change_24h = self._change_24h(status_dataset, current_quote.price) if status_dataset else None
        volume = getattr(current_quote, "volume", None) if getattr(current_quote, "volume", None) is not None else status_dataset.completed_candles[-1].volume if status_dataset else None
        status = MarketStatus(current_price=current_quote.price, change_24h_percent=change_24h, volume=volume, volatility_percent=volatility, technical_structure=structure_label, trend=trend, momentum=momentum, support=support, resistance=resistance, market_regime=market_regime)
        mtf: list[ReportTimeframe] = []
        if config.multi_timeframe_enabled:
            for timeframe in REPORT_TIMEFRAMES:
                dataset = datasets.get(timeframe)
                if dataset is None:
                    continue
                features = calculate_feature_set(dataset)
                tf_regime = detect_regime(dataset) if len(dataset.completed_candles) >= MIN_REPORT_CANDLES else None
                tf_support, tf_resistance = self._support_resistance(dataset)
                mtf.append(ReportTimeframe(timeframe=dataset.timeframe.value, trend=str(features.indicators.get("trend") or "UNKNOWN"), momentum=self._momentum(features.indicators), support=tf_support, resistance=tf_resistance, regime=tf_regime.regime.value if tf_regime else "UNKNOWN", latest_candle_timestamp=dataset.latest_completed_candle.timestamp))
        fundamental = FundamentalContext()
        if config.fundamental_analysis_enabled or config.news_analysis_enabled:
            try:
                news = await self.news_service.research(symbol=symbol, days=1, limit=12)
                fundamental = FundamentalContext(news_count=len(news.news) if config.news_analysis_enabled else 0, macro_count=sum(e.event_type.value == "MACRO" for e in news.fundamental_events) if config.fundamental_analysis_enabled else 0, event_count=len(news.fundamental_events) if config.fundamental_analysis_enabled else 0, headlines=[item.headline for item in news.news[:5]] if config.news_analysis_enabled else [])
            except (RuntimeError, ValueError, asyncio.TimeoutError):
                pass
        score, basis = self._score(status, mtf, fundamental)
        bull = [f"Primary trend is {status.trend.lower()}." if status.trend != "NOT_REQUESTED" else "Technical trend was not requested.", f"Market regime is {status.market_regime}." if status.market_regime != "NOT_REQUESTED" else "Market regime was not requested.", f"{sum(x.trend == 'BULLISH' for x in mtf)}/{len(mtf)} timeframes are bullish." if mtf else "Multi-timeframe analysis was not requested."]
        bear = [f"Primary momentum is {status.momentum.lower()}." if status.momentum != "NOT_REQUESTED" else "Technical momentum was not requested.", f"Resistance is near {resistance:.6g}." if resistance else "Resistance is unavailable.", "A regime transition or structural break would weaken the thesis."]
        risks = ["News and macro events can invalidate technical structure rapidly.", "Provider freshness or incomplete candles can reduce report confidence.", "The research score is deterministic and is not a probability of profit."]
        invalidation = [f"Bull thesis invalidation: sustained price below support {support:.6g}." if support else "Bull thesis invalidation: loss of the latest validated support.", "Bear thesis invalidation: confirmed bullish structure break above resistance."]
        interpretation = None
        if config.ai_interpretation_enabled:
            interpretation = f"{symbol} currently has a {status.trend.lower()} technical trend, {status.momentum.lower()} momentum, and a {status.market_regime} regime. The interpretation is assembled from the requested deterministic evidence and does not infer causation from headlines."
        return ResearchReport(symbol=symbol, generated_at=datetime.now(timezone.utc), request_configuration=self._configuration_model(config), market_status=status, indicators=technical_indicators, regime_snapshot=regime_snapshot, smc_structure=self._smc(primary_structure.events) if primary_structure else SMCStructure(), multi_timeframe=mtf, fundamental_context=fundamental, ai_interpretation=interpretation, bull_case=bull, bear_case=bear, key_risks=risks, invalidation=invalidation, overall_research_score=score, score_basis=basis)
