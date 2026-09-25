from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.models.market import OHLCVDataset
from app.models.quant_lab import BacktestResult, ExperimentSpec, StrategyDefinition
from app.services.entitlement import require_feature
from app.services.quant_lab import create_portfolio, list_portfolios, list_trades, run_backtest

router = APIRouter(prefix="/api/quant-lab", tags=["quant-lab"])


class BacktestRequest(BaseModel):
    strategy: StrategyDefinition
    experiment: ExperimentSpec
    dataset: OHLCVDataset


class PortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_currency: str = Field(default="USD", min_length=3, max_length=8)
    starting_equity: float = Field(gt=0)


def _token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return token


@router.post("/backtests", response_model=BacktestResult, dependencies=[Depends(_require_csrf)])
async def backtest(
    payload: BacktestRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return run_backtest(_token(access_token), user.id, payload.strategy, payload.dataset, payload.experiment)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/portfolios")
async def portfolios(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"items": list_portfolios(_token(access_token), user.id)}


@router.post("/portfolios", dependencies=[Depends(_require_csrf)])
async def portfolio(
    payload: PortfolioRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    require_feature(token, user.id, "basic_portfolio")
    return {"item": create_portfolio(token, user.id, payload.model_dump())}


@router.get("/portfolios/{portfolio_id}/trades")
async def trades(
    portfolio_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"items": list_trades(_token(access_token), user.id, portfolio_id)}
