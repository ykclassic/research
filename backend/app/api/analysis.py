from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, model_validator

from app.api.auth import get_current_user_or_github_actions
from app.config import settings
from app.models import Quote
from app.models.market import CompletenessStatus, FreshnessStatus, Timeframe
from app.services.feature_engine import calculate_feature_set
from app.services.indicator_series import calculate_indicator_panes
from app.services.quote_service import QuoteService
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/analysis", tags=["analysis"], dependencies=[Depends(get_current_user_or_github_actions)])
quote_service = QuoteService()


class CandleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    is_complete: bool


class IndicatorPoint(BaseModel):
    timestamp: datetime
    value: float | None = None


class IndicatorPane(BaseModel):
    id: str
    title: str
    unit: str
    min: float | None = None
    max: float | None = None
    points: list[IndicatorPoint]


class AnalysisQuality(BaseModel):
    request_latency_ms: int | None
    freshness_status: FreshnessStatus
    freshness_age_seconds: float | None
    candle_completeness: CompletenessStatus
    provenance_provider: str
    provider_attempts: tuple[str, ...]
    fallback_used: bool
    cache_hit: bool
    research_eligible: bool


class AnalysisResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    source: str
    calculated_at: datetime
    latest_candle_timestamp: datetime
    candle_count: int
    candles: list[CandleResponse]
    current_quote: Quote
    indicators: dict[str, float | str | None]
    indicator_panes: list[IndicatorPane]
    data_quality: AnalysisQuality

    @model_validator(mode="after")
    def validate_timestamp_consistency(self) -> "AnalysisResponse":
        completed = [candle for candle in self.candles if candle.is_complete]
        if not completed:
            raise ValueError("Analysis response must contain at least one completed candle.")
        if self.latest_candle_timestamp != completed[-1].timestamp:
            raise ValueError("Analysis latest_candle_timestamp must equal the latest completed candle timestamp.")
        if self.candle_count != len(completed):
            raise ValueError("Analysis candle_count must equal the number of completed candles.")
        if self.current_quote.symbol != self.symbol:
            raise ValueError("Current quote symbol must match analysis symbol.")
        for pane in self.indicator_panes:
            timestamps = [point.timestamp for point in pane.points]
            if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
                raise ValueError(f"Indicator-pane timestamps must be strictly increasing for {pane.id}.")
        return self


def normalize_range_boundary(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=422, detail=f"{field_name} must include a timezone.")
    return value.astimezone(timezone.utc)


@router.get("/{symbol:path}", response_model=AnalysisResponse)
async def get_analysis(
    symbol: str,
    timeframe: Timeframe = Query(Timeframe.HOUR_1),
    limit: int = Query(250, ge=50, le=5000),
    start: datetime | None = Query(None, description="Inclusive historical range start in ISO-8601 format."),
    end: datetime | None = Query(None, description="Inclusive historical range end in ISO-8601 format."),
):
    start = normalize_range_boundary(start, "start")
    end = normalize_range_boundary(end, "end")
    if (start is None) != (end is None):
        raise HTTPException(status_code=422, detail="Both start and end are required for a historical range.")
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=422, detail="Historical range start must be before end.")

    try:
        mapping = normalize_symbol(symbol)
        if start is None and end is None:
            # Preserve the narrow provider contract used by existing callers and
            # test doubles. Historical-range arguments are only supplied when
            # the request explicitly asks for a range.
            candle_task = quote_service.orchestrator.get_candles(
                mapping.internal,
                timeframe,
                limit,
            )
        else:
            candle_task = quote_service.orchestrator.get_candles(
                mapping.internal,
                timeframe,
                limit,
                start_date=start,
                end_date=end,
            )
        dataset, current_quote = await asyncio.wait_for(
            asyncio.gather(
                candle_task,
                quote_service.get_quote(mapping.internal, force_refresh=True),
            ),
            timeout=settings.analysis_timeout_seconds,
        )
        result = calculate_feature_set(dataset)
        candles = [CandleResponse.model_validate(candle) for candle in dataset.candles]
        completed = [candle for candle in candles if candle.is_complete]
        if not completed:
            raise ValueError("Provider returned no completed candles for analysis.")
        indicator_panes = calculate_indicator_panes(completed)
        quality = AnalysisQuality(
            request_latency_ms=dataset.request_latency_ms,
            freshness_status=dataset.freshness_status,
            freshness_age_seconds=dataset.freshness_age_seconds,
            candle_completeness=dataset.completeness_status,
            provenance_provider=dataset.source,
            provider_attempts=dataset.provider_attempts,
            fallback_used=dataset.fallback_used or current_quote.fallback_used,
            cache_hit=dataset.cache_hit or current_quote.cache_hit,
            research_eligible=(
                dataset.freshness_status in {FreshnessStatus.FRESH, FreshnessStatus.DELAYED}
                and dataset.completeness_status != CompletenessStatus.INVALID
                and current_quote.status.value in {"LIVE", "DELAYED"}
            ),
        )
        return AnalysisResponse(
            symbol=result.symbol,
            timeframe=result.timeframe,
            source=result.source,
            calculated_at=result.calculated_at,
            latest_candle_timestamp=completed[-1].timestamp,
            candle_count=len(completed),
            candles=candles,
            current_quote=current_quote,
            indicators=result.indicators,
            indicator_panes=indicator_panes,
            data_quality=quality,
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Market-data providers exceeded the analysis latency budget and no cached analysis was available.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
