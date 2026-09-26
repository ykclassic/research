from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.supabase_data import service_request

CHART_EVENT_TYPES = {"REGIME","SMC","BOS","CHOCH","LIQUIDITY","SIGNAL","ENTRY","EXIT","SL","TP","OUTCOME","RESEARCH","CATALYST"}
FUNDAMENTAL_TYPES = {"FINANCIAL_STATEMENT","EARNINGS","VALUATION","ANALYST_REVISION","CORPORATE_ACTION","FUNDAMENTAL_TREND"}
MODEL_TYPES = {"SIGNAL_CALIBRATION","QUALITY_SCORING","SIMILARITY","REGIME_CONDITIONED","PREDICTIVE"}

def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _rows(path: str, params: dict[str,str] | None = None) -> list[dict[str,Any]]: return service_request("GET",path,params=params).json()
def _one(path: str, params: dict[str,str]) -> dict[str,Any]:
    rows=_rows(path,params)
    if not rows: raise KeyError(path)
    return rows[0]

def create_chart_event(user_id: str, payload: dict[str,Any]) -> dict[str,Any]:
    event_type=str(payload.get("event_type","")).upper()
    if event_type not in CHART_EVENT_TYPES: raise ValueError("Unsupported chart event type.")
    symbol=str(payload.get("symbol","")).strip()
    if not symbol: raise ValueError("Symbol is required.")
    return service_request("POST","research_chart_events",json={"user_id":user_id,"symbol":symbol.upper(),"timeframe":str(payload.get("timeframe","H1")).upper(),"event_type":event_type,"occurred_at":payload.get("occurred_at") or _now(),"price":payload.get("price"),"payload":payload.get("payload") or {},"source":payload.get("source"),"engine_version":payload.get("engine_version") or "phase10-chart-events-v1"},prefer="return=representation").json()[0]

def list_chart_events(user_id: str, symbol: str, timeframe: str, limit: int=500) -> list[dict[str,Any]]:
    return _rows("research_chart_events",{"select":"*","user_id":f"eq.{user_id}","symbol":f"eq.{symbol.strip().upper()}","timeframe":f"eq.{timeframe.upper()}","order":"occurred_at.asc","limit":str(limit)})

def create_fundamental_observation(user_id: str, payload: dict[str,Any]) -> dict[str,Any]:
    observation_type=str(payload.get("observation_type","")).upper()
    if observation_type not in FUNDAMENTAL_TYPES: raise ValueError("Unsupported fundamental observation type.")
    symbol=str(payload.get("symbol","")).strip()
    if not symbol: raise ValueError("Symbol is required.")
    return service_request("POST","fundamental_observations",json={"user_id":user_id,"symbol":symbol.upper(),"observation_type":observation_type,"period_start":payload.get("period_start"),"period_end":payload.get("period_end"),"observed_at":payload.get("observed_at") or _now(),"source":payload.get("source"),"source_version":payload.get("source_version"),"payload":payload.get("payload") or {}},prefer="return=representation").json()[0]

def list_fundamentals(user_id: str, symbol: str, limit: int=200) -> list[dict[str,Any]]:
    return _rows("fundamental_observations",{"select":"*","user_id":f"eq.{user_id}","symbol":f"eq.{symbol.strip().upper()}","order":"observed_at.desc","limit":str(limit)})

def create_model(user_id: str, payload: dict[str,Any]) -> dict[str,Any]:
    model_type=str(payload.get("model_type","")).upper()
    if model_type not in MODEL_TYPES: raise ValueError("Unsupported model type.")
    return service_request("POST","research_models",json={"user_id":user_id,"name":str(payload["name"]).strip(),"model_type":model_type,"description":payload.get("description")},prefer="return=representation").json()[0]

def create_model_version(user_id: str, model_id: str, payload: dict[str,Any]) -> dict[str,Any]:
    _one("research_models",{"id":f"eq.{model_id}","user_id":f"eq.{user_id}"})
    row={"model_id":model_id,"user_id":user_id,"version":str(payload["version"]).strip(),"status":"DRAFT","dataset_version":str(payload["dataset_version"]).strip(),"feature_version":str(payload["feature_version"]).strip(),"training_period_start":payload["training_period_start"],"training_period_end":payload["training_period_end"],"validation_period_start":payload["validation_period_start"],"validation_period_end":payload["validation_period_end"],"test_period_start":payload["test_period_start"],"test_period_end":payload["test_period_end"],"calibration":payload.get("calibration") or {},"test_results":payload.get("test_results") or {},"performance_by_regime":payload.get("performance_by_regime") or {},"degradation_monitoring":payload.get("degradation_monitoring") or {}}
    version=service_request("POST","research_model_versions",json=row,prefer="return=representation").json()[0]
    service_request("POST","research_model_events",json={"model_version_id":version["id"],"user_id":user_id,"event_type":"CREATED","actor_user_id":user_id,"details":{"version":version["version"]}})
    return version

def list_models(user_id: str) -> list[dict[str,Any]]:
    models=_rows("research_models",{"select":"*","user_id":f"eq.{user_id}","order":"created_at.desc"})
    for model in models: model["versions"]=_rows("research_model_versions",{"select":"*","model_id":f"eq.{model['id']}","user_id":f"eq.{user_id}","order":"created_at.desc"})
    return models

def evaluate_model_version(user_id: str, version_id: str, test_results: dict[str,Any], calibration: dict[str,Any], performance_by_regime: dict[str,Any], degradation_monitoring: dict[str,Any]) -> dict[str,Any]:
    _one("research_model_versions",{"id":f"eq.{version_id}","user_id":f"eq.{user_id}"})
    sample_size=int(test_results.get("sample_size",0) or 0)
    calibration_error=float(calibration.get("error",1.0) or 1.0)
    regime_count=len(performance_by_regime)
    degradation_status=str(degradation_monitoring.get("status","UNKNOWN")).upper()
    passed=sample_size>=100 and calibration_error<=0.20 and regime_count>=1 and degradation_status not in {"DEGRADED","FAILED"}
    updated=service_request("PATCH","research_model_versions",params={"id":f"eq.{version_id}","user_id":f"eq.{user_id}"},json={"status":"VALIDATING","test_results":test_results,"calibration":calibration,"performance_by_regime":performance_by_regime,"degradation_monitoring":degradation_monitoring,"test_passed":passed},prefer="return=representation").json()[0]
    service_request("POST","research_model_events",json={"model_version_id":version_id,"user_id":user_id,"event_type":"EVALUATED","actor_user_id":user_id,"details":{"test_passed":passed,"sample_size":sample_size,"calibration_error":calibration_error}})
    return updated

def promote_model_version(user_id: str, version_id: str) -> dict[str,Any]:
    version=_one("research_model_versions",{"id":f"eq.{version_id}","user_id":f"eq.{user_id}"})
    if not version.get("test_passed"): raise ValueError("Model version cannot be promoted until validation records test_passed=true.")
    model=_one("research_models",{"id":f"eq.{version['model_id']}","user_id":f"eq.{user_id}"})
    active=model.get("active_version_id")
    if active: service_request("PATCH","research_model_versions",params={"id":f"eq.{active}","user_id":f"eq.{user_id}"},json={"status":"RETIRED"})
    promoted=service_request("PATCH","research_model_versions",params={"id":f"eq.{version_id}","user_id":f"eq.{user_id}"},json={"status":"APPROVED","promotion_actor_user_id":user_id,"promoted_at":_now()},prefer="return=representation").json()[0]
    service_request("PATCH","research_models",params={"id":f"eq.{model['id']}","user_id":f"eq.{user_id}"},json={"active_version_id":version_id})
    service_request("POST","research_model_events",json={"model_version_id":version_id,"user_id":user_id,"event_type":"PROMOTED","actor_user_id":user_id,"details":{"manual":True}})
    return promoted

def rollback_model_version(user_id: str, version_id: str, reason: str) -> dict[str,Any]:
    version=_one("research_model_versions",{"id":f"eq.{version_id}","user_id":f"eq.{user_id}"})
    model=_one("research_models",{"id":f"eq.{version['model_id']}","user_id":f"eq.{user_id}"})
    result=service_request("PATCH","research_model_versions",params={"id":f"eq.{version_id}","user_id":f"eq.{user_id}"},json={"status":"ROLLED_BACK","rollback_reason":reason.strip()},prefer="return=representation").json()[0]
    if model.get("active_version_id")==version_id: service_request("PATCH","research_models",params={"id":f"eq.{model['id']}","user_id":f"eq.{user_id}"},json={"active_version_id":None})
    service_request("POST","research_model_events",json={"model_version_id":version_id,"user_id":user_id,"event_type":"ROLLED_BACK","actor_user_id":user_id,"details":{"reason":reason}})
    return result

def track_product_event(user_id: str, event_name: str, feature: str|None, properties: dict[str,Any]) -> dict[str,Any]:
    return service_request("POST","product_events",json={"user_id":user_id,"event_name":event_name,"feature":feature,"properties":properties}).json()[0]

def overview(user_id: str) -> dict[str,Any]:
    models=list_models(user_id)
    chart_count=len(_rows("research_chart_events",{"select":"id","user_id":f"eq.{user_id}","limit":"1000"}))
    fundamental_count=len(_rows("fundamental_observations",{"select":"id","user_id":f"eq.{user_id}","limit":"1000"}))
    event_count=len(_rows("product_events",{"select":"id","user_id":f"eq.{user_id}","limit":"1000"}))
    statuses={status:sum(1 for m in models for v in m.get("versions",[]) if v.get("status")==status) for status in ("DRAFT","VALIDATING","APPROVED","RETIRED","ROLLED_BACK")}
    return {"model_governance":{"models":len(models),"versions_by_status":statuses,"automatic_promotion":False},"advanced_charting":{"events":chart_count,"event_types":sorted(CHART_EVENT_TYPES)},"fundamental_intelligence":{"observations":fundamental_count,"types":sorted(FUNDAMENTAL_TYPES)},"product_intelligence":{"tracked_events":event_count},"optimization":{"cache_namespace":"phase10","maintenance":"scheduler-ready"}}

def run_maintenance() -> dict[str,int]:
    expired=_rows("research_cache_entries",{"select":"cache_key","expires_at":f"lt.{_now()}"})
    for row in expired: service_request("DELETE","research_cache_entries",params={"cache_key":f"eq.{row['cache_key']}"})
    return {"expired_cache_entries":len(expired)}
