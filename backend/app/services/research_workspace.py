from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.market import Timeframe
from app.services.supabase_data import DataRequestError, _request
from app.services.entitlement import require_feature
from app.services.quote_service import QuoteService

quote_service = QuoteService()
TIMEFRAMES = {"1h": Timeframe.HOUR_1, "4h": Timeframe.HOUR_4, "1d": Timeframe.DAY_1}

def _get(resource: str, token: str, user_id: str, **extra: str) -> list[dict[str, Any]]:
    params = {"select": "*", "user_id": f"eq.{user_id}", **extra}
    return _request("GET", resource, token, params=params).json()

def _one(resource: str, token: str, user_id: str, row: dict[str, Any]) -> dict[str, Any]:
    payload = {**row, "user_id": user_id}
    result = _request("POST", resource, token, json=payload, prefer="return=representation").json()
    if not result: raise DataRequestError(f"{resource} could not be created.")
    return result[0]

def list_workspaces(token: str, user_id: str) -> list[dict[str, Any]]:
    return _get("research_workspaces", token, user_id, order="updated_at.desc", limit="100")

def create_workspace(token: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_feature(token, user_id, "advanced_research")
    return _one("research_workspaces", token, user_id, payload)

def update_workspace(token: str, user_id: str, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = _request("PATCH", "research_workspaces", token, params={"id": f"eq.{workspace_id}", "user_id": f"eq.{user_id}"}, json={**payload, "updated_at": datetime.now(timezone.utc).isoformat()}, prefer="return=representation").json()
    if not result: raise KeyError(workspace_id)
    return result[0]

def delete_workspace(token: str, user_id: str, workspace_id: str) -> None:
    _request("DELETE", "research_workspaces", token, params={"id": f"eq.{workspace_id}", "user_id": f"eq.{user_id}"})

def snapshot(token: str, user_id: str, workspace_id: str) -> dict[str, Any]:
    workspace = _request("GET", "research_workspaces", token, params={"select":"*","id":f"eq.{workspace_id}","user_id":f"eq.{user_id}"}).json()
    if not workspace: raise KeyError(workspace_id)
    return {
        "workspace": workspace[0],
        "assets": _request("GET","research_workspace_assets",token,params={"select":"*","workspace_id":f"eq.{workspace_id}","user_id":f"eq.{user_id}","order":"created_at.asc"}).json(),
        "dashboards": _request("GET","research_workspace_dashboards",token,params={"select":"*","workspace_id":f"eq.{workspace_id}","user_id":f"eq.{user_id}","order":"updated_at.desc"}).json(),
        "links": _request("GET","research_workspace_links",token,params={"select":"*","workspace_id":f"eq.{workspace_id}","user_id":f"eq.{user_id}","order":"created_at.desc"}).json(),
        "scorecards": _request("GET","research_scorecards",token,params={"select":"*","workspace_id":f"eq.{workspace_id}","user_id":f"eq.{user_id}","order":"updated_at.desc"}).json(),
        "automation": _request("GET","research_automation_rules",token,params={"select":"*","workspace_id":f"eq.{workspace_id}","user_id":f"eq.{user_id}","order":"created_at.desc"}).json(),
    }

def add_asset(token: str, user_id: str, workspace_id: str, symbol: str, role: str) -> dict[str, Any]:
    require_feature(token, user_id, "advanced_research")
    return _one("research_workspace_assets", token, user_id, {"workspace_id": workspace_id, "symbol": symbol.strip().upper().replace("-","/"), "role": role})

def remove_asset(token: str, user_id: str, workspace_id: str, symbol: str) -> None:
    _request("DELETE","research_workspace_assets",token,params={"workspace_id":f"eq.{workspace_id}","symbol":f"eq.{symbol}","user_id":f"eq.{user_id}"})

def upsert_dashboard(token: str, user_id: str, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_feature(token, user_id, "advanced_research")
    existing = _request("GET","research_workspace_dashboards",token,params={"select":"id","workspace_id":f"eq.{workspace_id}","user_id":f"eq.{user_id}","name":f"eq.{payload['name']}" }).json()
    if existing:
        result = _request("PATCH","research_workspace_dashboards",token,params={"id":f"eq.{existing[0]['id']}","user_id":f"eq.{user_id}"},json={**payload,"updated_at":datetime.now(timezone.utc).isoformat()},prefer="return=representation").json()
    else:
        result = _request("POST","research_workspace_dashboards",token,json={"user_id":user_id,"workspace_id":workspace_id,**payload},prefer="return=representation").json()
    return result[0]

def link_resource(token: str, user_id: str, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_feature(token, user_id, "advanced_research")
    return _one("research_workspace_links",token,user_id,{"workspace_id":workspace_id,**payload})

def create_scorecard(token: str,user_id: str,workspace_id: str,payload: dict[str,Any]) -> dict[str,Any]:
    require_feature(token,user_id,"advanced_research")
    return _one("research_scorecards",token,user_id,{"workspace_id":workspace_id,**payload})

async def evaluate_scorecard(token: str,user_id: str,scorecard: dict[str,Any],symbol: str) -> dict[str,Any]:
    factors=scorecard.get("factors") or []
    scores=[]; total_weight=0.0; weighted=0.0
    try:
        mapping=__import__("app.symbols",fromlist=["normalize_symbol"]).normalize_symbol(symbol)
        dataset=await quote_service.orchestrator.get_candles(mapping.internal,Timeframe.DAY_1,90)
        closes=[float(c.close) for c in dataset.completed_candles if c.close>0]
        momentum=((closes[-1]/closes[-20])-1)*100 if len(closes)>=20 else None
        volatility=None
        if len(closes)>=21:
            returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
            mean=sum(returns)/len(returns)
            volatility=math.sqrt(sum((r-mean)**2 for r in returns)/(len(returns)-1))*math.sqrt(252)*100
    except Exception:
        momentum=volatility=None
    context={"momentum_percent":momentum,"volatility_percent":volatility}
    for factor in factors:
        key=str(factor.get("field","")).strip()
        weight=float(factor.get("weight",1))
        value=context.get(key)
        target=factor.get("target")
        direction=factor.get("direction","positive")
        if value is None: continue
        raw=float(value if target is None else (value-target))
        contribution=raw if direction=="positive" else -raw
        scores.append({"factor":key,"value":value,"weight":weight,"contribution":contribution})
        weighted += contribution*weight; total_weight += abs(weight)
    score=weighted/total_weight if total_weight else 0.0
    return {"symbol":symbol,"score":score,"factors":scores,"context":context,"scorecard_id":scorecard["id"],"evaluated_at":datetime.now(timezone.utc).isoformat()}

async def cross_asset(token: str,user_id: str,workspace_id: str,symbols:list[str],timeframe:str) -> dict[str,Any]:
    require_feature(token,user_id,"advanced_research")
    tf=TIMEFRAMES[timeframe]
    series={}
    for symbol in symbols:
        try:
            mapping=__import__("app.symbols",fromlist=["normalize_symbol"]).normalize_symbol(symbol)
            dataset=await quote_service.orchestrator.get_candles(mapping.internal,tf,120)
            closes=[float(c.close) for c in dataset.completed_candles if c.close>0]
            series[symbol]=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
        except Exception:
            series[symbol]=[]
    matrix={s:{} for s in symbols}
    for i,left in enumerate(symbols):
        for right in symbols[i:]:
            if left==right: c=1.0
            else:
                n=min(len(series[left]),len(series[right]))
                if n<20: continue
                x,y=series[left][-n:],series[right][-n:]; mx,my=sum(x)/n,sum(y)/n
                vx=sum((v-mx)**2 for v in x); vy=sum((v-my)**2 for v in y)
                c=sum((a-mx)*(b-my) for a,b in zip(x,y))/math.sqrt(vx*vy) if vx and vy else 0.0
            matrix[left][right]=matrix[right][left]=round(max(-1,min(1,c)),4)
    relationships=[]
    for i,left in enumerate(symbols):
        for right in symbols[i+1:]:
            if right in matrix[left]:
                relationships.append({"left":left,"right":right,"correlation":matrix[left][right],"relationship":"COUPLED" if abs(matrix[left][right])>=0.7 else "DIVERGENT" if matrix[left][right]<=-0.4 else "LOOSE"})
    result={"workspace_id":workspace_id,"symbols":symbols,"timeframe":timeframe,"correlation_matrix":matrix,"relationships":relationships,"factor_relationships":[],"regime_relationships":[],"calculated_at":datetime.now(timezone.utc).isoformat()}
    _one("research_cross_asset_runs",token,user_id,{"workspace_id":workspace_id,"symbols":symbols,"timeframe":timeframe,"correlation_matrix":matrix,"relationships":relationships})
    return result

def create_automation(token: str,user_id: str,workspace_id: str,payload:dict[str,Any]) -> dict[str,Any]:
    require_feature(token,user_id,"scheduled_workflows")
    row = {"workspace_id":workspace_id, **payload}
    if row.get("trigger_type") == "SCHEDULE" and not row.get("next_run_at"):
        row["next_run_at"] = (datetime.now(timezone.utc) + __import__("datetime").timedelta(hours=1)).isoformat()
    return _one("research_automation_rules",token,user_id,row)

def diagnosis(token: str,user_id: str,experiment_id: str) -> dict[str,Any]:
    require_feature(token,user_id,"advanced_research")
    rows=_request("GET","quant_experiments",token,params={"select":"id,strategy_id,strategy_version,metrics,parameters,created_at","id":f"eq.{experiment_id}","user_id":f"eq.{user_id}"}).json()
    if not rows: raise KeyError(experiment_id)
    row=rows[0]; metrics=row.get("metrics") or {}; trades=int(metrics.get("trades",row.get("trade_count",0)) or 0)
    warnings=[]
    if trades<30: warnings.append("Sample weakness: fewer than 30 trades.")
    if float(metrics.get("max_drawdown",0) or 0)>abs(float(metrics.get("net_pnl",0) or 0)): warnings.append("Drawdown is large relative to net P&L.")
    regime=metrics.get("regime_breakdown") or {}
    if regime:
        dominant=max(regime.items(),key=lambda item: item[1].get("trades",0))
        if dominant[1].get("trades",0)/max(trades,1)>=0.7: warnings.append(f"Regime dependence: {dominant[0]} contains most observed trades.")
    return {"experiment_id":experiment_id,"strategy_id":row["strategy_id"],"strategy_version":row["strategy_version"],"performance_decay":None,"regime_dependence":bool(regime),"parameter_instability":None,"signal_quality_deterioration":None,"warnings":warnings,"limitations":["Diagnosis is deterministic from persisted experiment metrics; absent longitudinal observations, decay and parameter instability are not inferable."]}

def list_cross_asset(token: str,user_id: str,workspace_id: str) -> list[dict[str,Any]]:
    return _get("research_cross_asset_runs",token,user_id,workspace_id=f"eq.{workspace_id}",order="created_at.desc",limit="20")


async def run_due_automation_rules(token: str) -> dict[str,int]:
    now=datetime.now(timezone.utc)
    due=_request("GET","research_automation_rules",token,params={"select":"*","enabled":"eq.true","trigger_type":"eq.SCHEDULE","next_run_at":f"lte.{now.isoformat()}","limit":"500"}).json()
    completed=failed=0
    from app.services.research_copilot import ResearchCopilotService
    copilot=ResearchCopilotService()
    for rule in due:
        try:
            action=rule.get("action") or {}
            if action.get("type","RESEARCH_RUN") == "RESEARCH_RUN":
                query=action.get("query") or f"Research intelligence for {rule.get('symbol') or 'workspace assets'}"
                await copilot.run(token,rule["user_id"],query,rule.get("symbol") or "BTC/USD")
            _request("PATCH","research_automation_rules",token,params={"id":f"eq.{rule['id']}"},json={"last_triggered_at":now.isoformat(),"next_run_at":(now.replace(minute=0,second=0,microsecond=0)+__import__("datetime").timedelta(days=1)).isoformat()})
            completed+=1
        except Exception:
            failed+=1
    return {"scheduled":len(due),"completed":completed,"failed":failed}
