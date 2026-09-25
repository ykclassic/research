from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.models.research_workspace import (
    AutomationRuleCreate, CrossAssetRequest, DashboardUpsert, ScorecardCreate,
    ScorecardEvaluationRequest, StrategyDiagnosisRequest, WorkspaceAsset,
    WorkspaceCreate, WorkspaceLink, WorkspaceUpdate,
)
from app.services.entitlement import FeatureNotEntitledError, require_feature
from app.services.research_workspace import (
    add_asset, create_automation, create_scorecard, create_workspace, cross_asset,
    delete_workspace, diagnosis, evaluate_scorecard, link_resource, list_cross_asset,
    list_workspaces, remove_asset, snapshot, update_workspace, upsert_dashboard,
)
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/research-workspaces", tags=["research-workspaces"])

def _token(value: str | None) -> str:
    if not value: raise HTTPException(status_code=401, detail="Authentication required.")
    return value

def _advanced(token: str, user_id: str) -> str:
    try: require_feature(token,user_id,"advanced_research")
    except FeatureNotEntitledError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc
    return token

@router.get("")
async def workspaces(user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"items": list_workspaces(_advanced(_token(access_token),user.id),user.id)}

@router.post("", dependencies=[Depends(_require_csrf)])
async def workspace(payload: WorkspaceCreate,user: Annotated[UserResponse,Depends(get_current_user)],access_token: Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"item":create_workspace(_advanced(_token(access_token),user.id),user.id,payload.model_dump())}

@router.patch("/{workspace_id}", dependencies=[Depends(_require_csrf)])
async def edit(workspace_id:str,payload:WorkspaceUpdate,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    try:return {"item":update_workspace(_advanced(_token(access_token),user.id),user.id,workspace_id,payload.model_dump(exclude_none=True))}
    except KeyError as exc:raise HTTPException(status_code=404,detail="Workspace not found.") from exc

@router.delete("/{workspace_id}",dependencies=[Depends(_require_csrf)],status_code=204,response_model=None)
async def remove(workspace_id:str,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    delete_workspace(_advanced(_token(access_token),user.id),user.id,workspace_id)

@router.get("/{workspace_id}")
async def detail(workspace_id:str,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    try:return snapshot(_advanced(_token(access_token),user.id),user.id,workspace_id)
    except KeyError as exc:raise HTTPException(status_code=404,detail="Workspace not found.") from exc

@router.post("/{workspace_id}/assets",dependencies=[Depends(_require_csrf)])
async def asset(workspace_id:str,payload:WorkspaceAsset,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"item":add_asset(_advanced(_token(access_token),user.id),user.id,workspace_id,payload.symbol,payload.role)}

@router.delete("/{workspace_id}/assets/{symbol}",dependencies=[Depends(_require_csrf)],status_code=204,response_model=None)
async def asset_remove(workspace_id:str,symbol:str,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    remove_asset(_advanced(_token(access_token),user.id),user.id,workspace_id,symbol)

@router.post("/{workspace_id}/dashboards",dependencies=[Depends(_require_csrf)])
async def dashboard(workspace_id:str,payload:DashboardUpsert,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"item":upsert_dashboard(_advanced(_token(access_token),user.id),user.id,workspace_id,payload.model_dump())}

@router.post("/{workspace_id}/links",dependencies=[Depends(_require_csrf)])
async def link(workspace_id:str,payload:WorkspaceLink,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"item":link_resource(_advanced(_token(access_token),user.id),user.id,workspace_id,payload.model_dump())}

@router.post("/{workspace_id}/scorecards",dependencies=[Depends(_require_csrf)])
async def scorecard(workspace_id:str,payload:ScorecardCreate,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"item":create_scorecard(_advanced(_token(access_token),user.id),user.id,workspace_id,payload.model_dump())}

@router.post("/{workspace_id}/scorecards/{scorecard_id}/evaluate")
async def scorecard_evaluate(workspace_id:str,scorecard_id:str,payload:ScorecardEvaluationRequest,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    token=_advanced(_token(access_token),user.id)
    rows=snapshot(token,user.id,workspace_id)["scorecards"]
    card=next((x for x in rows if x["id"]==scorecard_id),None)
    if not card: raise HTTPException(status_code=404,detail="Scorecard not found.")
    return {"item":await evaluate_scorecard(token,user.id,card,payload.symbol)}

@router.post("/{workspace_id}/automation",dependencies=[Depends(_require_csrf)])
async def automation(workspace_id:str,payload:AutomationRuleCreate,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    token=_token(access_token)
    try: require_feature(token,user.id,"scheduled_workflows")
    except FeatureNotEntitledError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc
    return {"item":create_automation(token,user.id,workspace_id,payload.model_dump())}

@router.post("/{workspace_id}/cross-asset",dependencies=[Depends(_require_csrf)])
async def cross_asset_analysis(workspace_id:str,payload:CrossAssetRequest,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"item":await cross_asset(_advanced(_token(access_token),user.id),user.id,workspace_id,payload.symbols,payload.timeframe)}

@router.get("/{workspace_id}/cross-asset")
async def cross_asset_history(workspace_id:str,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    return {"items":list_cross_asset(_advanced(_token(access_token),user.id),user.id,workspace_id)}

@router.post("/strategy-diagnosis",dependencies=[Depends(_require_csrf)])
async def strategy_diagnosis(payload:StrategyDiagnosisRequest,user:Annotated[UserResponse,Depends(get_current_user)],access_token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    try:return {"item":diagnosis(_advanced(_token(access_token),user.id),user.id,payload.experiment_id)}
    except KeyError as exc:raise HTTPException(status_code=404,detail="Experiment not found.") from exc
