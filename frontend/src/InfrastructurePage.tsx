import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Copy, Download, KeyRound, Link2, Plus, RefreshCw, ShieldCheck, Trash2, Users } from "lucide-react";
import {
  API_KEY_SCOPES, WEBHOOK_EVENTS, createInfrastructureKey, createInfrastructureOrganization,
  createInfrastructureWebhook, deleteInfrastructureWebhook, getInfrastructureAudit,
  getInfrastructureKeys, getInfrastructureMembers, getInfrastructureOrganizations,
  getInfrastructureShares, InfrastructureApiKey, InfrastructureAudit, InfrastructureMember,
  InfrastructureOrganization, InfrastructureShare, InfrastructureWebhook, InfrastructureExportSchedule, revokeInfrastructureKey,
  shareInfrastructureResource, addInfrastructureMember, updateInfrastructureMember, getInfrastructureExportSchedules, createInfrastructureExportSchedule, deleteInfrastructureExportSchedule,
} from "./api";

const scopeDefaults=["market:read","research:read","signals:read","regimes:read","outcomes:read","analytics:read","runs:read","snapshots:read","exports:read","org:read"];
const resourceTypes=["WORKSPACE","DASHBOARD","WATCHLIST","REPORT","RESEARCH_RUN","SNAPSHOT"];

export default function InfrastructurePage() {
  const [keys,setKeys]=useState<InfrastructureApiKey[]>([]);
  const [webhooks,setWebhooks]=useState<InfrastructureWebhook[]>([]);
  const [orgs,setOrgs]=useState<InfrastructureOrganization[]>([]);
  const [org,setOrg]=useState<InfrastructureOrganization|null>(null);
  const [members,setMembers]=useState<InfrastructureMember[]>([]);
  const [shares,setShares]=useState<InfrastructureShare[]>([]);
  const [audit,setAudit]=useState<InfrastructureAudit[]>([]);\n  const [exportSchedules,setExportSchedules]=useState<InfrastructureExportSchedule[]>([]);\n  const [exportName,setExportName]=useState("Daily research dataset");\n  const [exportResource,setExportResource]=useState("RUNS");\n  const [exportFormat,setExportFormat]=useState("JSON");\n  const [exportInterval,setExportInterval]=useState(1440);
  const [keyName,setKeyName]=useState("Research integration");
  const [scopes,setScopes]=useState(scopeDefaults);
  const [newSecret,setNewSecret]=useState<string|null>(null);
  const [hookName,setHookName]=useState("Research events");
  const [hookUrl,setHookUrl]=useState("");
  const [hookEvents,setHookEvents]=useState(["research.completed","outcome.event"]);
  const [hookSecret,setHookSecret]=useState<string|null>(null);
  const [orgName,setOrgName]=useState("My Research Team");
  const [memberUserId,setMemberUserId]=useState("");
  const [memberRole,setMemberRole]=useState("viewer");
  const [shareType,setShareType]=useState("WORKSPACE");
  const [shareId,setShareId]=useState("");
  const [sharePermission,setSharePermission]=useState("VIEW");
  const [error,setError]=useState<string|null>(null);
  const [busy,setBusy]=useState(false);

  const load=useCallback(async()=>{
    try {
      setError(null);
      const [k,w,o,e]=await Promise.all([getInfrastructureKeys(),getInfrastructureWebhooks(),getInfrastructureOrganizations(),getInfrastructureExportSchedules()]);
      setKeys(k); setWebhooks(w); setOrgs(o); setExportSchedules(e);
      const selected=org && o.some(item=>item.id===org.id) ? o.find(item=>item.id===org.id)! : o[0]??null;
      setOrg(selected);
      if(selected){
        const [m,s,a]=await Promise.all([getInfrastructureMembers(selected.id),getInfrastructureShares(selected.id),getInfrastructureAudit(selected.id)]);
        setMembers(m);setShares(s);setAudit(a);
      } else { setMembers([]);setShares([]);setAudit([]); }
    } catch(e) {
      setError(e instanceof Error?e.message:"Unable to load infrastructure controls.");
    }
  },[org]);

  useEffect(()=>{void load();},[load]);

  const createKey=async()=>{
    try{setBusy(true);const item=await createInfrastructureKey({name:keyName,scopes});setNewSecret(item.secret);setKeyName("");await load();}catch(e){setError(e instanceof Error?e.message:"Unable to create API key.");}finally{setBusy(false);}
  };
  const createHook=async()=>{
    try{setBusy(true);const item=await createInfrastructureWebhook({name:hookName,url:hookUrl,events:hookEvents});setHookSecret(item.secret);setHookUrl("");await load();}catch(e){setError(e instanceof Error?e.message:"Unable to create webhook.");}finally{setBusy(false);}
  };
  const createOrg=async()=>{
    try{setBusy(true);const item=await createInfrastructureOrganization(orgName);setOrg(item);setOrgName("");await load();}catch(e){setError(e instanceof Error?e.message:"Unable to create organization.");}finally{setBusy(false);}
  };
  const addMember=async()=>{
    if(!org||!memberUserId.trim())return;
    try{setBusy(true);await addInfrastructureMember(org.id,memberUserId.trim(),memberRole);setMemberUserId("");await load();}catch(e){setError(e instanceof Error?e.message:"Unable to add member.");}finally{setBusy(false);}
  };
  const createExportSchedule=async()=>{try{setBusy(true);await createInfrastructureExportSchedule({name:exportName,resource_type:exportResource,format:exportFormat,interval_minutes:exportInterval});setExportName("");await load();}catch(e){setError(e instanceof Error?e.message:"Unable to create export schedule.");}finally{setBusy(false);}};
  const share=async()=>{
    if(!org||!shareId.trim())return;
    try{setBusy(true);await shareInfrastructureResource(org.id,{resource_type:shareType,resource_id:shareId.trim(),permission:sharePermission});setShareId("");await load();}catch(e){setError(e instanceof Error?e.message:"Unable to share resource.");}finally{setBusy(false);}
  };
  const toggleScope=(scope:string)=>setScopes(current=>current.includes(scope)?current.filter(x=>x!==scope):[...current,scope]);
  const toggleEvent=(event:string)=>setHookEvents(current=>current.includes(event)?current.filter(x=>x!==event):[...current,event]);

  return <div className="app phase9-page"><main>
    <section className="hero">
      <div><div className="eyebrow">Phase 9 · Premium infrastructure</div><h2>Research infrastructure control plane.</h2><p>Programmable access, event delivery, reproducible datasets and organization-level collaboration around the same research system.</p></div>
      <div className="hero-stat"><ShieldCheck size={20}/><strong>API · MCP · Webhooks</strong><span>controlled infrastructure</span></div>
    </section>
    {error&&<div className="error" role="alert"><AlertTriangle size={17}/>{error}</div>}
    {newSecret&&<section className="panel phase9-secret"><div><strong>New API key — copy it now</strong><span>The secret is shown once and is not returned by the key list.</span></div><code>{newSecret}</code><button onClick={()=>void navigator.clipboard?.writeText(newSecret)}><Copy size={15}/>Copy</button></section>}
    {hookSecret&&<section className="panel phase9-secret"><div><strong>New webhook signing secret — copy it now</strong><span>Webhook deliveries use HMAC-SHA256 with a timestamped payload.</span></div><code>{hookSecret}</code><button onClick={()=>void navigator.clipboard?.writeText(hookSecret)}><Copy size={15}/>Copy</button></section>}

    <section className="panel"><div className="panel-head"><div><h3><KeyRound size={17}/> API access</h3><span>Scoped bearer keys for external applications and research pipelines.</span></div><button className="refresh" onClick={()=>void load()} disabled={busy}><RefreshCw size={15}/>Refresh</button></div>
      <div className="phase9-form"><label>Name<input value={keyName} onChange={e=>setKeyName(e.target.value)} placeholder="Integration name"/></label><div><strong>Scopes</strong><div className="phase9-chips">{API_KEY_SCOPES.map(scope=><button type="button" className={scopes.includes(scope)?"active":""} key={scope} onClick={()=>toggleScope(scope)}>{scope}</button>)}</div></div><button onClick={()=>void createKey()} disabled={busy||!keyName.trim()||!scopes.length}><Plus size={15}/>Create API key</button></div>
      {!keys.length?<div className="settings-health-empty">No API keys yet.</div>:<div className="phase9-list">{keys.map(k=><article key={k.id}><div><strong>{k.name}</strong><span>{k.key_prefix} · {k.scopes.length} scopes · {k.active?"active":"revoked"}</span></div>{k.active&&<button className="icon-button danger" onClick={()=>void revokeInfrastructureKey(k.id)}><Trash2 size={14}/></button>}</article>)}</div>}
    </section>

    <section className="panel"><div className="panel-head"><div><h3><Link2 size={17}/> Webhook event delivery</h3><span>Queued, signed events with retry state; delivery runs through the existing research scheduler.</span></div></div>
      <div className="phase9-form"><label>Name<input value={hookName} onChange={e=>setHookName(e.target.value)}/></label><label>Endpoint URL<input value={hookUrl} onChange={e=>setHookUrl(e.target.value)} placeholder="https://example.com/research-events"/></label><div><strong>Events</strong><div className="phase9-chips">{WEBHOOK_EVENTS.map(event=><button type="button" className={hookEvents.includes(event)?"active":""} key={event} onClick={()=>toggleEvent(event)}>{event}</button>)}</div></div><button onClick={()=>void createHook()} disabled={busy||!hookName.trim()||!hookUrl.trim()||!hookEvents.length}><Plus size={15}/>Create webhook</button></div>
      {!webhooks.length?<div className="settings-health-empty">No webhook endpoints configured.</div>:<div className="phase9-list">{webhooks.map(w=><article key={w.id}><div><strong>{w.name}</strong><span>{w.url} · {w.events.join(", ")} · failures {w.failure_count}</span></div><button className="icon-button danger" onClick={()=>void deleteInfrastructureWebhook(w.id)}><Trash2 size={14}/></button></article>)}</div>}
    </section>

    <section className="panel"><div className="panel-head"><div><h3><Users size={17}/> Team collaboration</h3><span>Organizations, roles, shared research resources and an audit trail.</span></div></div>
      <div className="phase9-form"><label>New organization<input value={orgName} onChange={e=>setOrgName(e.target.value)} placeholder="Organization name"/></label><button onClick={()=>void createOrg()} disabled={busy||!orgName.trim()}><Plus size={15}/>Create organization</button></div>
      {orgs.length>0&&<label className="phase9-select">Organization<select value={org?.id??""} onChange={e=>setOrg(orgs.find(item=>item.id===e.target.value)??null)}>{orgs.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      {org&&<><div className="phase9-form"><label>Member user ID<input value={memberUserId} onChange={e=>setMemberUserId(e.target.value)} placeholder="Supabase user UUID"/></label><label>Role<select value={memberRole} onChange={e=>setMemberRole(e.target.value)}><option>viewer</option><option>editor</option><option>admin</option></select></label><button onClick={()=>void addMember()} disabled={busy||!memberUserId.trim()}><Plus size={15}/>Add member</button></div>
      <div className="phase9-list">{members.map(m=><article key={m.id}><div><strong>{m.user_id}</strong><span>{m.role}</span></div>{m.role!=="owner"&&<select value={m.role} onChange={e=>void updateInfrastructureMember(org.id,m.id,e.target.value)}><option>viewer</option><option>editor</option><option>admin</option></select>}</article>)}</div>
      <div className="phase9-form"><label>Share resource type<select value={shareType} onChange={e=>setShareType(e.target.value)}>{resourceTypes.map(t=><option key={t}>{t}</option>)}</select></label><label>Resource ID<input value={shareId} onChange={e=>setShareId(e.target.value)} placeholder="UUID"/></label><label>Permission<select value={sharePermission} onChange={e=>setSharePermission(e.target.value)}><option>VIEW</option><option>EDIT</option><option>ADMIN</option></select></label><button onClick={()=>void share()} disabled={busy||!shareId.trim()}><Plus size={15}/>Share</button></div>
      <div className="phase9-subgrid"><div><h4>Shared resources</h4>{!shares.length?<p className="muted">No shared resources yet.</p>:shares.map(s=><div className="phase9-mini" key={s.id}><strong>{s.resource_type}</strong><span>{s.resource_id} · {s.permission}</span></div>)}</div><div><h4>Audit trail</h4>{!audit.length?<p className="muted">No organization actions yet.</p>:audit.slice(0,8).map(a=><div className="phase9-mini" key={a.id}><strong>{a.action}</strong><span>{a.actor_user_id??"system"} · {new Date(a.created_at).toLocaleString()}</span></div>)}</div></div></>}
    </section>


    <section className="panel"><div className="panel-head"><div><h3><Download size={17}/> Scheduled exports</h3><span>Recurring JSON/CSV snapshots are persisted with dataset, feature, engine and model versions.</span></div></div>
      <div className="phase9-form"><label>Name<input value={exportName} onChange={e=>setExportName(e.target.value)} placeholder="Daily export"/></label><label>Dataset<select value={exportResource} onChange={e=>setExportResource(e.target.value)}><option>RUNS</option><option>SNAPSHOTS</option><option>OUTCOMES</option></select></label><label>Format<select value={exportFormat} onChange={e=>setExportFormat(e.target.value)}><option>JSON</option><option>CSV</option></select></label><label>Interval<select value={exportInterval} onChange={e=>setExportInterval(Number(e.target.value))}><option value={60}>Hourly</option><option value={360}>Every 6 hours</option><option value={1440}>Daily</option><option value={10080}>Weekly</option></select></label><button onClick={()=>void createExportSchedule()} disabled={busy||!exportName.trim()}><Plus size={15}/>Schedule export</button></div>
      {!exportSchedules.length?<div className="settings-health-empty">No scheduled exports.</div>:<div className="phase9-list">{exportSchedules.map(s=><article key={s.id}><div><strong>{s.name}</strong><span>{s.resource_type} · {s.format} · next {new Date(s.next_run_at).toLocaleString()}</span></div><button className="icon-button danger" onClick={()=>void deleteInfrastructureExportSchedule(s.id)}><Trash2 size={14}/></button></article>)}</div>}
    </section>
    <section className="panel"><div className="panel-head"><div><h3><Download size={17}/> Machine-readable exports & reproducibility</h3><span>JSON/CSV datasets preserve version metadata alongside research state.</span></div></div>
      <div className="phase9-export-grid">{[["RUNS","Research runs"],["SNAPSHOTS","Research snapshots"],["OUTCOMES","Signal outcomes"]].map(([id,label])=><article key={id}><strong>{label}</strong><span>JSON and CSV</span><div><button onClick={()=>window.open(`/api/infrastructure/export/${id.toLowerCase()}?format=json`,"_blank")}>JSON</button><button onClick={()=>window.open(`/api/infrastructure/export/${id.toLowerCase()}?format=csv`,"_blank")}>CSV</button></div></article>)}</div>
      <div className="phase9-contract"><strong>External contracts</strong><code>GET /api/v1/market/quote/:symbol</code><code>GET /api/v1/research/runs</code><code>GET /api/v1/research/snapshots</code><code>GET /api/v1/signals</code><code>GET /api/v1/regimes/:symbol</code><code>GET /api/v1/outcomes</code><code>GET /api/v1/portfolio/analytics</code><code>GET /api/v1/exports/:resource?format=csv</code><code>POST /api/mcp</code></div>
    </section>
    <footer>Infrastructure access is scoped and metered. Webhook signatures use HMAC-SHA256. Research snapshots record dataset, feature, engine and model versions where available.</footer>
  </main></div>;
}
