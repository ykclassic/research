from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.services.entitlement import FeatureNotEntitledError, require_feature
from app.services.phase10_intelligence import (
    create_chart_event, create_fundamental_observation, create_model, create_model_version,
    evaluate_model_version, list_chart_events, list_fundamentals, list_models, overview,
    promote_model_version, rollback_model_version, track_product_event,
)

router = APIRouter(prefix="/api/phase10", tags=["phase10"])


def _feature(token: str, user_id: str) -> None:
    try:
        require_feature(token, user_id, "phase10_intelligence")
    except FeatureNotEntitledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


class ChartEventCreate(BaseModel):
    symbol: str = Field(min_length=2, max_length=32)
    timeframe: str = Field(default="H1", min_length=1, max_length=8)
    event_type: str
    occurred_at: str | None = None
    price: float | None = None
    payload: dict = Field(default_factory=dict)
    source: str | None = None
    engine_version: str | None = None


class FundamentalCreate(BaseModel):
    symbol: str = Field(min_length=2, max_length=32)
    observation_type: str
    period_start: str | None = None
    period_end: str | None = None
    observed_at: str | None = None
    source: str | None = None
    source_version: str | None = None
    payload: dict = Field(default_factory=dict)


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    model_type: str
    description: str | None = None


class ModelVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    dataset_version: str
    feature_version: str
    training_period_start: str
    training_period_end: str
    validation_period_start: str
    validation_period_end: str
    test_period_start: str
    test_period_end: str
    calibration: dict = Field(default_factory=dict)
    test_results: dict = Field(default_factory=dict)
    performance_by_regime: dict = Field(default_factory=dict)
    degradation_monitoring: dict = Field(default_factory=dict)


class ModelEvaluate(BaseModel):
    test_results: dict = Field(default_factory=dict)
    calibration: dict = Field(default_factory=dict)
    performance_by_regime: dict = Field(default_factory=dict)
    degradation_monitoring: dict = Field(default_factory=dict)


class RollbackRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ProductEvent(BaseModel):
    event_name: str = Field(min_length=1, max_length=120)
    feature: str | None = Field(default=None, max_length=120)
    properties: dict = Field(default_factory=dict)


def _auth(user: Annotated[UserResponse, Depends(get_current_user)], token: Annotated[str | None, Cookie(alias="mr_access_token")] = None) -> tuple[UserResponse, str]:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    _feature(token, user.id)
    return user, token


@router.get("/overview")
async def get_overview(auth: tuple[UserResponse, str] = Depends(_auth)):
    return overview(auth[0].id)


@router.get("/chart-events")
async def get_chart_events(symbol: str = Query(min_length=2, max_length=32), timeframe: str = Query("H1", min_length=1, max_length=8), limit: int = Query(500, ge=1, le=2000), auth: tuple[UserResponse, str] = Depends(_auth)):
    return {"items": list_chart_events(auth[0].id, symbol, timeframe, limit)}


@router.post("/chart-events", dependencies=[Depends(_require_csrf)])
async def post_chart_event(payload: ChartEventCreate, auth: tuple[UserResponse, str] = Depends(_auth)):
    try:
        return {"item": create_chart_event(auth[0].id, payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/fundamentals")
async def get_fundamentals(symbol: str = Query(min_length=2, max_length=32), limit: int = Query(200, ge=1, le=1000), auth: tuple[UserResponse, str] = Depends(_auth)):
    return {"items": list_fundamentals(auth[0].id, symbol, limit)}


@router.post("/fundamentals", dependencies=[Depends(_require_csrf)])
async def post_fundamental(payload: FundamentalCreate, auth: tuple[UserResponse, str] = Depends(_auth)):
    try:
        return {"item": create_fundamental_observation(auth[0].id, payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/models")
async def get_models(auth: tuple[UserResponse, str] = Depends(_auth)):
    return {"items": list_models(auth[0].id)}


@router.post("/models", dependencies=[Depends(_require_csrf)])
async def post_model(payload: ModelCreate, auth: tuple[UserResponse, str] = Depends(_auth)):
    try:
        return {"item": create_model(auth[0].id, payload.model_dump())}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/versions", dependencies=[Depends(_require_csrf)])
async def post_model_version(model_id: str, payload: ModelVersionCreate, auth: tuple[UserResponse, str] = Depends(_auth)):
    try:
        return {"item": create_model_version(auth[0].id, model_id, payload.model_dump())}
    except (ValueError, KeyError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/model-versions/{version_id}/evaluate", dependencies=[Depends(_require_csrf)])
async def post_model_evaluation(version_id: str, payload: ModelEvaluate, auth: tuple[UserResponse, str] = Depends(_auth)):
    try:
        return {"item": evaluate_model_version(auth[0].id, version_id, payload.test_results, payload.calibration, payload.performance_by_regime, payload.degradation_monitoring)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/model-versions/{version_id}/promote", dependencies=[Depends(_require_csrf)])
async def post_model_promotion(version_id: str, auth: tuple[UserResponse, str] = Depends(_auth)):
    try:
        return {"item": promote_model_version(auth[0].id, version_id)}
    except (KeyError, ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/model-versions/{version_id}/rollback", dependencies=[Depends(_require_csrf)])
async def post_model_rollback(version_id: str, payload: RollbackRequest, auth: tuple[UserResponse, str] = Depends(_auth)):
    try:
        return {"item": rollback_model_version(auth[0].id, version_id, payload.reason)}
    except (KeyError, ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/events", dependencies=[Depends(_require_csrf)])
async def post_product_event(payload: ProductEvent, auth: tuple[UserResponse, str] = Depends(_auth)):
    return {"item": track_product_event(auth[0].id, payload.event_name, payload.feature, payload.properties)}
