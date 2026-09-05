from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.analysis import get_analysis
from app.api.auth import _require_csrf, get_current_user_or_github_actions
from app.api.market_structure import get_market_structure
from app.api.mtf import get_multi_timeframe_analysis
from app.api.regime import get_regime
from app.models.market import Timeframe
from app.services.ai_research import AIResearchError, AIResearchService

router = APIRouter(
    prefix="/api/ai-research",
    tags=["ai-research"],
    dependencies=[Depends(get_current_user_or_github_actions), Depends(_require_csrf)],
)
ai_service = AIResearchService()


class AIResearchRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    timeframe: Timeframe = Timeframe.HOUR_1
    limit: int = Field(default=250, ge=50, le=5000)
    question: str | None = Field(default=None, max_length=2000)


class AIResearchResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    deterministic_gate: str
    verified_context: dict
    report: str
    model: str


@router.post("/report", response_model=AIResearchResponse)
async def create_ai_research(request: AIResearchRequest) -> AIResearchResponse:
    """Generate interpretation only after the deterministic research gate passes.

    Every value sent to the AI is produced server-side by the deterministic
    market-data, feature, regime, structure, and MTF layers. The client cannot
    submit its own market facts to this endpoint.
    """
    try:
        analysis = await get_analysis(request.symbol, request.timeframe, request.limit)
        if not analysis.data_quality.research_eligible:
            raise HTTPException(status_code=409, detail="AI research is disabled because the deterministic analysis dataset did not pass the research-eligibility gate.")
        regime = await get_regime(request.symbol, request.timeframe, max(request.limit, 220))
        structure = await get_market_structure(request.symbol, request.timeframe, request.limit)
        mtf = await get_multi_timeframe_analysis(request.symbol, request.limit)
        if analysis.latest_candle_timestamp != structure.latest_candle_timestamp:
            raise HTTPException(status_code=409, detail="AI research is disabled because the deterministic analysis and structure snapshots are not temporally aligned.")
        if mtf.symbol != analysis.symbol or len(mtf.timeframes) != 4:
            raise HTTPException(status_code=409, detail="AI research is disabled because the deterministic multi-timeframe context is incomplete.")

        context = {
            "context_version": "1.0",
            "evidence": [
                {"id": "TA", "type": "deterministic_technical_analysis", "source": analysis.source, "timeframe": analysis.timeframe.value, "latest_candle_timestamp": analysis.latest_candle_timestamp, "candle_count": analysis.candle_count, "current_quote": analysis.current_quote.model_dump(mode="json"), "indicators": analysis.indicators, "data_quality": analysis.data_quality.model_dump(mode="json")},
                {"id": "REGIME", "type": "deterministic_market_regime", "source": regime.source, "timeframe": regime.timeframe.value, "latest_candle_timestamp": regime.latest_candle_timestamp, "candle_count": regime.candle_count, "regime": regime.regime.value, "confidence": regime.confidence, "evidence": regime.evidence.model_dump(mode="json"), "thresholds": regime.thresholds.model_dump(mode="json"), "rule_id": regime.rule_id},
                {"id": "STRUCTURE", "type": "deterministic_market_structure", "source": structure.source, "timeframe": structure.timeframe.value, "latest_candle_timestamp": structure.latest_candle_timestamp, "candle_count": structure.candle_count, "events": [event.model_dump(mode="json") for event in structure.events]},
                {"id": "MTF", "type": "deterministic_multi_timeframe_research", "calculated_at": mtf.calculated_at, "timeframes": [item.model_dump(mode="json") for item in mtf.timeframes], "research": mtf.research.model_dump(mode="json")},
            ],
        }
        ai_result = await ai_service.interpret(context, request.question)
        return AIResearchResponse(symbol=analysis.symbol, timeframe=analysis.timeframe, deterministic_gate="PASSED", verified_context=context, report=ai_result["report"], model=ai_result["model"])
    except HTTPException:
        raise
    except AIResearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
