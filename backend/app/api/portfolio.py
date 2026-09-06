from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, status

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.models.portfolio import PortfolioPositionCreate, PortfolioPositionUpdate, RiskRewardRequest, ScenarioRequest
from app.services.portfolio import create_position, delete_position, list_positions, risk_reward, scenario, summarize, update_position
from app.services.supabase_data import DataServiceError
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


def _db_error(exc: DataServiceError) -> HTTPException:
    return HTTPException(status_code=503, detail="Portfolio persistence service is temporarily unavailable.")


@router.get("/positions")
async def get_positions(user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"positions": list_positions(_token(access_token), user.id)}
    except DataServiceError as exc:
        raise _db_error(exc) from exc


@router.post("/positions", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def add_position(payload: PortfolioPositionCreate, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        symbol = normalize_symbol(payload.symbol).internal
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized = payload.model_copy(update={"symbol": symbol})
    try:
        return create_position(_token(access_token), user.id, normalized)
    except DataServiceError as exc:
        raise _db_error(exc) from exc


@router.patch("/positions/{position_id}", dependencies=[Depends(_require_csrf)])
async def edit_position(position_id: str, payload: PortfolioPositionUpdate, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    if not payload.model_dump(exclude_unset=True):
        raise HTTPException(status_code=400, detail="At least one position field must be supplied for update.")
    if payload.symbol is not None:
        try:
            payload = payload.model_copy(update={"symbol": normalize_symbol(payload.symbol).internal})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return update_position(_token(access_token), user.id, position_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Portfolio position not found.") from exc
    except DataServiceError as exc:
        raise _db_error(exc) from exc


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def remove_position(position_id: str, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        delete_position(_token(access_token), user.id, position_id)
    except DataServiceError as exc:
        raise _db_error(exc) from exc


@router.get("/summary")
async def get_summary(user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return await summarize(_token(access_token), user.id)
    except DataServiceError as exc:
        raise _db_error(exc) from exc


@router.post("/scenario")
async def run_scenario(payload: ScenarioRequest, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        summary = await summarize(_token(access_token), user.id)
        return scenario(summary, payload.price_change_percent)
    except DataServiceError as exc:
        raise _db_error(exc) from exc


@router.post("/risk-reward")
async def calculate_risk_reward(payload: RiskRewardRequest, _: Annotated[UserResponse, Depends(get_current_user)]):
    return risk_reward(payload)
