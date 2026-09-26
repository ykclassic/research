from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.config import settings
from app.services.entitlement import FeatureNotEntitledError, require_feature
from app.services.phase9_infrastructure import (
    API_SCOPES, WEBHOOK_EVENTS, add_member, audit, authenticate_api_key, consume_api_request,
    create_api_key, create_organization, create_webhook, delete_webhook, ensure_org_access,
    export_rows, has_feature, list_audit, list_api_keys, list_members, list_organizations,
    list_shares, list_webhooks, revoke_api_key, share_resource, to_csv, update_member,
)
from app.services.supabase_data import service_request

router = APIRouter(prefix="/api", tags=["phase9"])

class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    scopes: list[str] = Field(min_length=1,max_length=20)
    expires_at: str | None = None

class WebhookCreate(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    url: str = Field(min_length=10,max_length=2048)
    events: list[str] = Field(min_length=1,max_length=10)

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1,max_length=120)

class MemberCreate(BaseModel):
    user_id: str
    role: str = "viewer"

class MemberUpdate(BaseModel):
    role: str

class ShareCreate(BaseModel):
    resource_type: str
    resource_id: str
    permission: str = "VIEW"

def _feature(token: str, user_id: str, name: str) -> None:
    try:
        require_feature(token,user_id,name)
    except FeatureNotEntitledError as exc:
        raise HTTPException(status_code=403,detail=str(exc)) from exc

def _api_key(authorization: str | None, scope: str) -> dict[str,Any]:
    if not authorization:
        raise HTTPException(status_code=401,detail="API key authentication required.")
    scheme,_,raw=authorization.partition(" ")
    if scheme.lower()!="bearer" or not raw.strip():
        raise HTTPException(status_code=401,detail="Use Authorization: Bearer <research-api-key>.")
    try:
        key=authenticate_api_key(raw.strip())
        if not has_feature(key["user_id"],"api"):
            raise PermissionError("API access is not enabled for this account.")
        if scope not in key.get("scopes",[]): raise PermissionError(f"API key lacks scope '{scope}'.")
        consume_api_request(key["user_id"])
        return key
    except PermissionError as exc:
        detail=str(exc)
        code=429 if "limit" in detail.lower() else 403
        raise HTTPException(status_code=code,detail=detail) from exc

def _api_auth(authorization: Annotated[str|None,Header(alias="Authorization")], scope: str) -> dict[str,Any]:
    return _api_key(authorization,scope)

@router.get("/infrastructure/keys")
async def get_keys(user: Annotated[UserResponse,Depends(get_current_user)], token: Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"api")
    return {"items":list_api_keys(user.id)}

@router.post("/infrastructure/keys",dependencies=[Depends(_require_csrf)])
async def post_key(payload:ApiKeyCreate,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"api")
    try:return {"item":create_api_key(user.id,payload.name,payload.scopes,payload.expires_at)}
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.delete("/infrastructure/keys/{key_id}",dependencies=[Depends(_require_csrf)],status_code=204)
async def delete_key(key_id:str,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"api"); revoke_api_key(user.id,key_id)

@router.get("/infrastructure/webhooks")
async def get_webhooks(user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"webhooks"); return {"items":list_webhooks(user.id),"events":sorted(WEBHOOK_EVENTS)}

@router.post("/infrastructure/webhooks",dependencies=[Depends(_require_csrf)])
async def post_webhook(payload:WebhookCreate,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"webhooks")
    try:return {"item":create_webhook(user.id,payload.name,payload.url,payload.events)}
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.delete("/infrastructure/webhooks/{webhook_id}",dependencies=[Depends(_require_csrf)],status_code=204)
async def remove_webhook(webhook_id:str,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"webhooks"); delete_webhook(user.id,webhook_id)

@router.get("/infrastructure/organizations")
async def get_orgs(user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces"); return {"items":list_organizations(user.id)}

@router.post("/infrastructure/organizations",dependencies=[Depends(_require_csrf)])
async def post_org(payload:OrganizationCreate,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces"); return {"item":create_organization(user.id,payload.name)}

@router.get("/infrastructure/organizations/{org_id}/members")
async def get_members(org_id:str,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces")
    try:return {"items":list_members(user.id,org_id)}
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc

@router.post("/infrastructure/organizations/{org_id}/members",dependencies=[Depends(_require_csrf)])
async def post_member(org_id:str,payload:MemberCreate,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces")
    try:return {"item":add_member(user.id,org_id,payload.user_id,payload.role)}
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.patch("/infrastructure/organizations/{org_id}/members/{member_id}",dependencies=[Depends(_require_csrf)])
async def patch_member(org_id:str,member_id:str,payload:MemberUpdate,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces")
    try:return {"item":update_member(user.id,org_id,member_id,payload.role)}
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
    except (ValueError,KeyError) as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.get("/infrastructure/organizations/{org_id}/shares")
async def get_shares(org_id:str,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces")
    try:return {"items":list_shares(user.id,org_id)}
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc

@router.post("/infrastructure/organizations/{org_id}/shares",dependencies=[Depends(_require_csrf)])
async def post_share(org_id:str,payload:ShareCreate,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces")
    try:return {"item":share_resource(user.id,org_id,payload.resource_type,payload.resource_id,payload.permission)}
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

@router.get("/infrastructure/organizations/{org_id}/audit")
async def get_audit(org_id:str,user:Annotated[UserResponse,Depends(get_current_user)],token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"team_workspaces")
    try:return {"items":list_audit(user.id,org_id)}
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc

@router.get("/v1/market/quote/{symbol:path}")
async def v1_market_quote(symbol:str, authorization:Annotated[str|None,Header(alias="Authorization")]=None):
    _api_key(authorization,"market:read")
    from app.services.quote_service import QuoteService
    quote=await QuoteService().get_quote(symbol)
    return {"data":quote.model_dump(mode="json"),"meta":{"version":"2026-09-26","source":quote.source,"observed_at":quote.observed_at}}

@router.get("/v1/research/runs")
async def v1_runs(authorization:Annotated[str|None,Header(alias="Authorization")]=None,limit:int=Query(50,ge=1,le=500)):
    key=_api_key(authorization,"runs:read")
    rows=export_rows(key["user_id"],"RUN","RUNS")
    return {"data":rows[:limit],"meta":{"count":min(len(rows),limit),"contract_version":"1.0"}}

@router.get("/v1/research/runs/{run_id}")
async def v1_run(run_id:str,authorization:Annotated[str|None,Header(alias="Authorization")]=None):
    key=_api_key(authorization,"runs:read")
    rows=service_request("GET","research_runs",params={"select":"*","id":f"eq.{run_id}","user_id":f"eq.{key['user_id']}"}).json()
    if not rows:raise HTTPException(status_code=404,detail="Research run not found.")
    return {"data":rows[0],"meta":{"contract_version":"1.0"}}

@router.get("/v1/research/snapshots")
async def v1_snapshots(authorization:Annotated[str|None,Header(alias="Authorization")]=None,limit:int=Query(50,ge=1,le=500)):
    key=_api_key(authorization,"snapshots:read"); rows=export_rows(key["user_id"],"SNAPSHOT","SNAPSHOTS")
    return {"data":rows[:limit],"meta":{"count":min(len(rows),limit),"contract_version":"1.0"}}

@router.get("/v1/signals")
async def v1_signals(authorization:Annotated[str|None,Header(alias="Authorization")]=None,limit:int=Query(50,ge=1,le=500)):
    key=_api_key(authorization,"signals:read")
    rows=service_request("GET","signal_intelligence",params={"select":"id,signal_id,symbol,direction,confidence,outcome,r_result,regime,signal_engine_version,dispatched_at,target_timestamp,stop_timestamp,first_touch_timestamp","user_id":f"eq.{key['user_id']}","order":"dispatched_at.desc","limit":str(limit)}).json()
    return {"data":rows,"meta":{"count":len(rows),"contract_version":"1.0"}}

@router.get("/v1/regimes/{symbol:path}")
async def v1_regime(symbol:str,authorization:Annotated[str|None,Header(alias="Authorization")]=None):
    key=_api_key(authorization,"regimes:read")
    from app.symbols import normalize_symbol
    from app.services.regime_detection import detect_regime
    from app.services.quote_service import QuoteService
    from app.models.market import Timeframe
    mapping=normalize_symbol(symbol); dataset=await QuoteService().orchestrator.get_candles(mapping.internal,Timeframe.HOUR_1,120)
    result=detect_regime(dataset)
    return {"data":{"symbol":symbol,"regime":result.regime.value,"confidence":float(result.confidence),"observed_at":dataset.completed_candles[-1].timestamp if dataset.completed_candles else None},"meta":{"contract_version":"1.0","api_user":key["user_id"]}}

@router.get("/v1/outcomes")
async def v1_outcomes(authorization:Annotated[str|None,Header(alias="Authorization")]=None,limit:int=Query(50,ge=1,le=500)):
    key=_api_key(authorization,"outcomes:read"); rows=export_rows(key["user_id"],"OUTCOME","OUTCOMES")
    return {"data":rows[:limit],"meta":{"count":min(len(rows),limit),"contract_version":"1.0"}}

@router.get("/v1/portfolio/analytics")
async def v1_portfolio(authorization:Annotated[str|None,Header(alias="Authorization")]=None):
    key=_api_key(authorization,"analytics:read")
    from app.services.portfolio import summarize
    from app.services.portfolio_intelligence import build_intelligence
    from app.models.portfolio import PortfolioSummary
    summary_row=await summarize(settings.supabase_service_role_key,key["user_id"])
    intelligence=await build_intelligence(settings.supabase_service_role_key,key["user_id"],summary_row)
    return {"data":intelligence.model_dump(mode="json"),"meta":{"contract_version":"1.0"}}

@router.get("/v1/exports/{resource}")
async def v1_export(resource:str,format:str=Query("json",pattern="^(json|csv)$"),authorization:Annotated[str|None,Header(alias="Authorization")]=None):
    key=_api_key(authorization,"exports:read")
    rows=export_rows(key["user_id"],"DATASET",resource.upper())
    if format=="csv":
        return Response(content=to_csv(rows),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=research-{resource.lower()}.csv"})
    return {"data":rows,"meta":{"format":"JSON","count":len(rows),"contract_version":"1.0"}}

@router.post("/mcp",dependencies=[])
async def mcp(request: dict[str,Any],authorization:Annotated[str|None,Header(alias="Authorization")]=None):
    key=_api_key(authorization,"mcp:read")
    method=request.get("method"); request_id=request.get("id")
    if method=="initialize":
        return {"jsonrpc":"2.0","id":request_id,"result":{"protocolVersion":"2025-06-18","serverInfo":{"name":"profitforge-research","version":"1.0"},"capabilities":{"tools":{}}}}
    if method=="tools/list":
        return {"jsonrpc":"2.0","id":request_id,"result":{"tools":[
            {"name":"market_quote","description":"Get a validated market quote.","inputSchema":{"type":"object","properties":{"symbol":{"type":"string"}},"required":["symbol"]}},
            {"name":"research_runs","description":"List persisted research runs.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer"}}}},
            {"name":"research_snapshots","description":"List reproducible research snapshots.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer"}}}},
            {"name":"portfolio_analytics","description":"Get portfolio intelligence for the authenticated API-key owner.","inputSchema":{"type":"object","properties":{}}}
        ]}}
    if method!="tools/call":
        return {"jsonrpc":"2.0","id":request_id,"error":{"code":-32601,"message":"Method not supported."}}
    params=request.get("params") or {}; name=params.get("name"); args=params.get("arguments") or {}
    if name=="market_quote":
        from app.services.quote_service import QuoteService
        result=(await QuoteService().get_quote(str(args.get("symbol") or ""))).model_dump(mode="json")
    elif name=="research_runs":
        result=export_rows(key["user_id"],"RUN","RUNS")[:max(1,min(int(args.get("limit",20)),100))]
    elif name=="research_snapshots":
        result=export_rows(key["user_id"],"SNAPSHOT","SNAPSHOTS")[:max(1,min(int(args.get("limit",20)),100))]
    elif name=="portfolio_analytics":
        from app.services.portfolio import summary
        from app.services.portfolio_intelligence import build_intelligence
        result=(await build_intelligence(settings.supabase_service_role_key,key["user_id"],await summarize(settings.supabase_service_role_key,key["user_id"]))).model_dump(mode="json")
    else:
        return {"jsonrpc":"2.0","id":request_id,"error":{"code":-32602,"message":"Unknown tool."}}
    return {"jsonrpc":"2.0","id":request_id,"result":{"content":[{"type":"text","text":json.dumps(result,default=str)}]}}

@router.get("/infrastructure/export/{resource}")
async def browser_export(resource:str,format:str=Query("json",pattern="^(json|csv)$"),user:Annotated[UserResponse,Depends(get_current_user)]=None,token:Annotated[str|None,Cookie(alias="mr_access_token")]=None):
    _feature(token or "",user.id,"exports")
    rows=export_rows(user.id,"DATASET",resource.upper())
    if format=="csv":return Response(content=to_csv(rows),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename={resource.lower()}.csv"})
    return {"data":rows,"meta":{"count":len(rows),"format":"JSON"}}
