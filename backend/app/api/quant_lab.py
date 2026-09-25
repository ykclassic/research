from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.models.market import OHLCVDataset
from app.models.quant_lab import BacktestResult, ExperimentSpec, StrategyDefinition, StrategyBuilderRequest, RobustnessResult, PaperBacktestComparison, PaperTrade
from app.services.entitlement import require_feature
from app.services.quant_lab import create_portfolio, list_portfolios, list_trades, run_backtest
from app.services.quant_validation import compare_paper_to_backtest, robustness, validate_strategy_definition
from app.services.supabase_data import _request

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


@router.post("/strategies", dependencies=[Depends(_require_csrf)])
async def save_strategy(
    payload: StrategyBuilderRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    require_feature(token, user.id, "strategy_builder")
    strategy = StrategyDefinition(**payload.model_dump())
    errors = validate_strategy_definition(strategy)
    if errors:
        raise HTTPException(status_code=422, detail=list(errors))
    row = _request(
        "POST", "strategy_definitions", token,
        json={"user_id": user.id, "name": strategy.name, "version": strategy.version, "definition": strategy.model_dump(mode="json")},
        prefer="return=representation",
    ).json()
    return {"item": strategy.model_copy(update={"id": str(row[0]["id"])})}


@router.get("/strategies")
async def saved_strategies(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    require_feature(token, user.id, "strategy_builder")
    rows = _request("GET", "strategy_definitions", token, params={"select":"id,name,version,definition,created_at","user_id":f"eq.{user.id}","order":"created_at.desc"}).json()
    return {"items": rows}


class RobustnessRequest(BaseModel):
    experiment: ExperimentSpec
    result: BacktestResult
    sensitivity_values: dict[str, list[float]] = Field(default_factory=dict)


@router.post("/robustness", response_model=RobustnessResult, dependencies=[Depends(_require_csrf)])
async def validate_robustness(
    payload: RobustnessRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    require_feature(token, user.id, "backtesting")
    if payload.result.spec_hash != payload.experiment.spec_hash:
        raise HTTPException(status_code=422, detail="Experiment and backtest result spec hashes must match.")
    return robustness(payload.result, payload.experiment, payload.sensitivity_values)


class PaperComparisonRequest(BaseModel):
    experiment_id: str
    result: BacktestResult
    paper_trades: list[PaperTrade]


@router.post("/paper-comparison", response_model=PaperBacktestComparison)
async def paper_comparison(
    payload: PaperComparisonRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    require_feature(token, user.id, "backtesting")
    return compare_paper_to_backtest(payload.result, payload.paper_trades, payload.experiment_id)
