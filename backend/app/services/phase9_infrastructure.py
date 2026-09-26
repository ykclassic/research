from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.services.supabase_data import DataRequestError, service_request

API_SCOPES = {
    "market:read","research:read","signals:read","regimes:read","outcomes:read",
    "analytics:read","runs:read","snapshots:read","exports:read","org:read","mcp:read"
}
WEBHOOK_EVENTS = {"signal.event","regime.change","watchpoint.trigger","research.completed","outcome.event"}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

def _service_token() -> str:
    if not settings.supabase_service_role_key:
        raise DataRequestError("Server-side database access is not configured.")
    return settings.supabase_service_role_key

def _rows(path: str, params: dict[str,str] | None = None) -> list[dict[str,Any]]:
    return service_request("GET", path, params=params).json()

def _one(path: str, params: dict[str,str]) -> dict[str,Any]:
    rows = _rows(path, params)
    if not rows:
        raise KeyError(path)
    return rows[0]

def _plan(user_id: str) -> str:
    rows = _rows("billing_subscriptions", {"select":"plan_id,status,trial_ends_at,updated_at","user_id":f"eq.{user_id}","status":"in.(trialing,active,past_due,unpaid,paused)","order":"updated_at.desc","limit":"1"})
    if not rows:
        return "free"
    row=rows[0]
    trial=row.get("trial_ends_at")
    if trial and trial <= _now():
        return "free"
    return str(row.get("plan_id") or "free")

def has_feature(user_id: str, feature: str) -> bool:
    plan=_plan(user_id)
    rows=_rows("billing_plan_features", {"select":"enabled","plan_id":f"eq.{plan}","feature_id":f"eq.{feature}","limit":"1"})
    return bool(rows and rows[0].get("enabled"))

def create_api_key(user_id: str, name: str, scopes: list[str], expires_at: str | None = None) -> dict[str,Any]:
    invalid=set(scopes)-API_SCOPES
    if invalid: raise ValueError(f"Unsupported API scopes: {', '.join(sorted(invalid))}")
    if not scopes: raise ValueError("At least one API scope is required.")
    raw="mrk_"+secrets.token_urlsafe(36)
    prefix=raw[:14]
    row={"user_id":user_id,"name":name.strip(),"key_prefix":prefix,"key_hash":_hash(raw),"scopes":sorted(set(scopes)),"expires_at":expires_at}
    created=service_request("POST","api_keys",json=row,prefer="return=representation").json()[0]
    return {**created,"secret":raw}

def list_api_keys(user_id: str) -> list[dict[str,Any]]:
    rows=_rows("api_keys",{"select":"id,name,key_prefix,scopes,active,last_used_at,expires_at,created_at,revoked_at","user_id":f"eq.{user_id}","order":"created_at.desc"})
    return rows

def revoke_api_key(user_id: str, key_id: str) -> None:
    service_request("PATCH","api_keys",params={"id":f"eq.{key_id}","user_id":f"eq.{user_id}"},json={"active":False,"revoked_at":_now()})

def authenticate_api_key(raw: str) -> dict[str,Any]:
    if not raw.startswith("mrk_") or len(raw)<20:
        raise PermissionError("Invalid API key.")
    prefix=raw[:14]
    rows=_rows("api_keys",{"select":"id,user_id,name,key_hash,scopes,active,expires_at","key_prefix":f"eq.{prefix}","active":"eq.true","limit":"1"})
    if not rows or not hmac.compare_digest(rows[0]["key_hash"],_hash(raw)):
        raise PermissionError("Invalid API key.")
    row=rows[0]
    if row.get("expires_at") and row["expires_at"] <= _now(): raise PermissionError("API key has expired.")
    service_request("PATCH","api_keys",params={"id":f"eq.{row['id']}"},json={"last_used_at":_now()})
    return row

def consume_api_request(user_id: str) -> dict[str,Any]:
    rows=service_request("POST","rpc/consume_api_usage",json={"p_user_id":user_id,"p_quantity":1}).json()
    if not rows or not rows[0].get("allowed"):
        raise PermissionError("API request limit reached.")
    return rows[0]

def queue_event(user_id: str, event_type: str, payload: dict[str,Any]) -> int:
    if event_type not in WEBHOOK_EVENTS: return 0
    endpoints=_rows("webhook_endpoints",{"select":"id,user_id","user_id":f"eq.{user_id}","active":"eq.true"})
    target=[e for e in endpoints if event_type in (_one("webhook_endpoints",{"id":f"eq.{e['id']}"}).get("events") or [])]
    if not target: return 0
    rows=[{"webhook_id":e["id"],"user_id":user_id,"event_type":event_type,"payload":payload} for e in target]
    response=service_request("POST","webhook_deliveries",json=rows,prefer="return=minimal")
    return len(target) if response.status_code in {200,201,204} else 0

def create_webhook(user_id: str, name: str, url: str, events: list[str]) -> dict[str,Any]:
    invalid=set(events)-WEBHOOK_EVENTS
    if invalid: raise ValueError(f"Unsupported webhook events: {', '.join(sorted(invalid))}")
    if not events: raise ValueError("At least one webhook event is required.")
    secret="whsec_"+secrets.token_urlsafe(30)
    row=service_request("POST","webhook_endpoints",json={"user_id":user_id,"name":name.strip(),"url":url.strip(),"events":sorted(set(events)),"secret":secret},prefer="return=representation").json()[0]
    return {**row,"secret":secret}

def list_webhooks(user_id: str) -> list[dict[str,Any]]:
    rows=_rows("webhook_endpoints",{"select":"id,name,url,events,active,failure_count,last_delivered_at,last_error,created_at,updated_at","user_id":f"eq.{user_id}","order":"created_at.desc"})
    return rows

def delete_webhook(user_id: str, webhook_id: str) -> None:
    service_request("DELETE","webhook_endpoints",params={"id":f"eq.{webhook_id}","user_id":f"eq.{user_id}"})

def deliver_pending_webhooks(limit: int = 50) -> dict[str,int]:
    now=_now()
    deliveries=_rows("webhook_deliveries",{"select":"id,webhook_id,user_id,event_type,payload,attempt_count","status":"eq.PENDING","next_attempt_at":f"lte.{now}","order":"created_at.asc","limit":str(limit)})
    delivered=failed=0
    for d in deliveries:
        try:
            endpoint=_one("webhook_endpoints",{"id":f"eq.{d['webhook_id']}","active":"eq.true"})
            body=json.dumps({"id":d["id"],"type":d["event_type"],"created_at":_now(),"data":d["payload"]},separators=(",",":"),sort_keys=True).encode()
            timestamp=str(int(datetime.now(timezone.utc).timestamp()))
            signature=hmac.new(endpoint["secret"].encode(),f"{timestamp}.".encode()+body,"sha256").hexdigest()
            response=httpx.post(endpoint["url"],content=body,headers={"Content-Type":"application/json","User-Agent":"Research-Infrastructure/1.0","X-Research-Event":d["event_type"],"X-Research-Timestamp":timestamp,"X-Research-Signature":f"v1={signature}"},timeout=10)
            if 200<=response.status_code<300:
                service_request("PATCH","webhook_deliveries",params={"id":f"eq.{d['id']}"},json={"status":"DELIVERED","attempt_count":int(d["attempt_count"])+1,"delivered_at":_now(),"response_status":response.status_code,"response_body":response.text[:2000]})
                service_request("PATCH","webhook_endpoints",params={"id":f"eq.{endpoint['id']}"},json={"failure_count":0,"last_delivered_at":_now(),"last_error":None})
                delivered+=1
            else: raise RuntimeError(f"HTTP {response.status_code}")
        except Exception as exc:
            attempt=int(d.get("attempt_count") or 0)+1
            status="FAILED" if attempt>=5 else "PENDING"
            delay_minutes=min(60, 2 ** min(attempt, 6))
            next_attempt=(datetime.now(timezone.utc).replace(microsecond=0) + __import__("datetime").timedelta(minutes=delay_minutes)).isoformat()
            service_request("PATCH","webhook_deliveries",params={"id":f"eq.{d['id']}"},json={"status":status,"attempt_count":attempt,"next_attempt_at":next_attempt,"response_body":str(exc)[:2000]})
            if endpoint:\n                service_request("PATCH","webhook_endpoints",params={"id":f"eq.{endpoint['id']}"},json={"failure_count":attempt,"last_error":str(exc)[:2000]})
            failed+=1
    return {"processed":len(deliveries),"delivered":delivered,"failed":failed}

def create_organization(user_id: str, name: str) -> dict[str,Any]:
    row=service_request("POST","organizations",json={"owner_user_id":user_id,"name":name.strip()},prefer="return=representation").json()[0]
    service_request("POST","organization_members",json={"organization_id":row["id"],"user_id":user_id,"role":"owner"})
    audit(user_id,row["id"],"organization.created","ORGANIZATION",row["id"],{"name":row["name"]})
    return row

def list_organizations(user_id: str) -> list[dict[str,Any]]:
    owned=_rows("organizations",{"select":"id,name,owner_user_id,created_at,updated_at","owner_user_id":f"eq.{user_id}","order":"created_at.desc"})
    memberships=_rows("organization_members",{"select":"organization_id","user_id":f"eq.{user_id}"})
    ids={str(row["id"]) for row in owned}|{str(row["organization_id"]) for row in memberships}
    if not ids: return []
    return _rows("organizations",{"select":"id,name,owner_user_id,created_at,updated_at","id":f"in.({','.join(sorted(ids))})","order":"created_at.desc"})

def list_members(user_id: str, org_id: str) -> list[dict[str,Any]]:
    ensure_org_access(user_id,org_id)
    return _rows("organization_members",{"select":"id,organization_id,user_id,role,created_at","organization_id":f"eq.{org_id}","order":"created_at.asc"})

def add_member(actor_user_id: str, org_id: str, member_user_id: str, role: str) -> dict[str,Any]:
    ensure_org_role(actor_user_id,org_id,{"owner","admin"})
    if role not in {"admin","editor","viewer"}: raise ValueError("Invalid member role.")
    row=service_request("POST","organization_members",json={"organization_id":org_id,"user_id":member_user_id,"role":role},prefer="return=representation").json()[0]
    audit(actor_user_id,org_id,"member.added","MEMBER",row["id"],{"user_id":member_user_id,"role":role})
    return row

def update_member(actor_user_id: str, org_id: str, member_id: str, role: str) -> dict[str,Any]:
    ensure_org_role(actor_user_id,org_id,{"owner","admin"})
    if role not in {"admin","editor","viewer"}: raise ValueError("Invalid member role.")
    row=service_request("PATCH","organization_members",params={"id":f"eq.{member_id}","organization_id":f"eq.{org_id}"},json={"role":role},prefer="return=representation").json()
    if not row: raise KeyError(member_id)
    audit(actor_user_id,org_id,"member.role_updated","MEMBER",member_id,{"role":role})
    return row[0]

def ensure_org_access(user_id: str, org_id: str) -> dict[str,Any]:
    org=_one("organizations",{"id":f"eq.{org_id}"})
    members=_rows("organization_members",{"select":"id,user_id,role","organization_id":f"eq.{org_id}","user_id":f"eq.{user_id}","limit":"1"})
    if org["owner_user_id"]!=user_id and not members: raise PermissionError("Organization access denied.")
    return members[0] if members else {"role":"owner","user_id":user_id}

def ensure_org_role(user_id: str, org_id: str, roles: set[str]) -> dict[str,Any]:
    membership=ensure_org_access(user_id,org_id)
    if membership["role"] not in roles: raise PermissionError("Insufficient organization permission.")
    return membership

def share_resource(user_id: str, org_id: str, resource_type: str, resource_id: str, permission: str="VIEW") -> dict[str,Any]:
    ensure_org_role(user_id,org_id,{"owner","admin","editor"})
    if resource_type not in {"WORKSPACE","DASHBOARD","WATCHLIST","REPORT","RESEARCH_RUN","SNAPSHOT"}: raise ValueError("Invalid resource type.")
    if permission not in {"VIEW","EDIT","ADMIN"}: raise ValueError("Invalid permission.")
    resource_table={"WORKSPACE":"research_workspaces","DASHBOARD":"research_workspace_dashboards","WATCHLIST":"watchlists","REPORT":"research_history","RESEARCH_RUN":"research_runs","SNAPSHOT":"research_snapshots"}[resource_type]
    owned=_rows(resource_table,{"select":"id,user_id","id":f"eq.{resource_id}","user_id":f"eq.{user_id}","limit":"1"})
    if not owned: raise PermissionError("Only the resource owner can share this resource.")
    row=service_request("POST","resource_shares",json={"organization_id":org_id,"shared_by_user_id":user_id,"resource_type":resource_type,"resource_id":resource_id,"permission":permission},prefer="return=representation").json()[0]
    audit(user_id,org_id,"resource.shared",resource_type,resource_id,{"permission":permission})
    return row

def list_shares(user_id: str, org_id: str) -> list[dict[str,Any]]:
    ensure_org_access(user_id,org_id)
    return _rows("resource_shares",{"select":"id,organization_id,shared_by_user_id,resource_type,resource_id,permission,created_at","organization_id":f"eq.{org_id}","order":"created_at.desc"})

def audit(actor_user_id: str, org_id: str | None, action: str, resource_type: str | None, resource_id: str | None, metadata: dict[str,Any] | None=None) -> None:
    service_request("POST","audit_log",json={"organization_id":org_id,"actor_user_id":actor_user_id,"action":action,"resource_type":resource_type,"resource_id":resource_id,"metadata":metadata or {}})

def list_audit(user_id: str, org_id: str) -> list[dict[str,Any]]:
    ensure_org_access(user_id,org_id)
    return _rows("audit_log",{"select":"id,organization_id,actor_user_id,action,resource_type,resource_id,metadata,created_at","organization_id":f"eq.{org_id}","order":"created_at.desc","limit":"200"})

def reproducibility_hash(state: dict[str,Any], dataset_version: str, feature_version: str, engine_version: str, model_version: str) -> str:
    canonical=json.dumps({"state":state,"dataset_version":dataset_version,"feature_version":feature_version,"engine_version":engine_version,"model_version":model_version},sort_keys=True,separators=(",",":"))
    return hashlib.sha256(canonical.encode()).hexdigest()

def export_rows(user_id: str, export_type: str, resource_type: str, resource_id: str | None=None) -> list[dict[str,Any]]:
    if resource_type=="RUNS":
        return _rows("research_runs",{"select":"id,query,assets,timeframe,model,model_version,engine_version,generated_report,metadata,created_at","user_id":f"eq.{user_id}","order":"created_at.desc","limit":"500"})
    if resource_type=="SNAPSHOTS":
        params={"select":"id,symbol,snapshot_type,snapshot_at,state,source_history_id,research_run_id,dataset_version,feature_version,engine_version,model_version,reproducibility_hash,created_at","user_id":f"eq.{user_id}","order":"snapshot_at.desc","limit":"500"}
        if resource_id: params["id"]=f"eq.{resource_id}"
        return _rows("research_snapshots",params)
    if resource_type=="OUTCOMES":
        return _rows("signal_intelligence",{"select":"id,signal_id,symbol,direction,confidence,outcome,r_result,signal_engine_version,dispatched_at,target_timestamp,stop_timestamp,first_touch_timestamp","user_id":f"eq.{user_id}","order":"dispatched_at.desc","limit":"500"})
    raise ValueError("Unsupported export resource.")

def to_csv(rows: list[dict[str,Any]]) -> str:
    if not rows: return ""
    keys=sorted({k for row in rows for k in row})
    output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=keys,extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k:(json.dumps(row.get(k),sort_keys=True) if isinstance(row.get(k),(dict,list)) else row.get(k)) for k in keys})
    return output.getvalue()
