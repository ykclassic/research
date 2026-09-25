import { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, BrainCircuit, CalendarClock, Plus, RefreshCw, Trash2 } from "lucide-react";
import {
  ApiError, ResearchWorkspace, ResearchWorkspaceSnapshot, addResearchWorkspaceAsset,
  createResearchAutomation, createResearchScorecard, createResearchWorkspace,
  deleteResearchWorkspace, evaluateResearchScorecard, getResearchWorkspace,
  getResearchWorkspaces, runCrossAssetResearch, saveResearchWorkspaceDashboard,
} from "./api";

const TYPES=["CRYPTO","EQUITIES","FX","SECTOR","STRATEGY","THEME","PORTFOLIO","CUSTOM"];

export default function ResearchWorkspacesPage(){
  const [workspaces,setWorkspaces]=useState<ResearchWorkspace[]>([]);
  const [active,setActive]=useState<string|null>(null);
  const [snapshot,setSnapshot]=useState<ResearchWorkspaceSnapshot|null>(null);
  const [name,setName]=useState(""); const [type,setType]=useState("THEME"); const [symbol,setSymbol]=useState("");
  const [error,setError]=useState<string|null>(null); const [busy,setBusy]=useState(false);
  const [crossAsset,setCrossAsset]=useState(""); const [scoreResult,setScoreResult]=useState<Record<string,any>|null>(null);

  const load=async(id?:string)=>{try{setError(null);const ws=await getResearchWorkspaces();setWorkspaces(ws);const next=id??active??ws[0]?.id??null;setActive(next);if(next)setSnapshot(await getResearchWorkspace(next));else setSnapshot(null);}catch(e){setError(e instanceof Error?e.message:"Unable to load research workspaces.");}};
  useEffect(()=>{void load();},[]);

  const create=async()=>{if(!name.trim())return;try{setBusy(true);const w=await createResearchWorkspace({name:name.trim(),workspace_type:type});setName("");await load(w.id);}catch(e){setError(e instanceof Error?e.message:"Unable to create workspace.");}finally{setBusy(false);}};
  const addAsset=async()=>{if(!active||!symbol.trim())return;try{await addResearchWorkspaceAsset(active,{symbol:symbol.trim(),role:"PRIMARY"});setSymbol("");await load(active);}catch(e){setError(e instanceof Error?e.message:"Unable to add asset.");}};
  const createDashboard=async()=>{if(!active)return;try{await saveResearchWorkspaceDashboard(active,{name:"Research Overview",layout:{columns:12,rows:[]},widgets:[{type:"MARKET_REGIME",title:"Market Regime"},{type:"RESEARCH_SCORE","title":"Research Score"},{type:"CORRELATION_MATRIX","title":"Cross-Asset Correlation"},{type:"CATALYSTS","title":"Catalysts"}],saved_views:[{name:"Default",filters:{}}],custom_metrics:[],shared:false});await load(active);}catch(e){setError(e instanceof Error?e.message:"Unable to save dashboard.");}};
  const createScore=async()=>{if(!active)return;try{await createResearchScorecard(active,{name:"Momentum & Volatility",factors:[{field:"momentum_percent",weight:0.6,direction:"positive"},{field:"volatility_percent",weight:-0.4,direction:"positive"}],conditions:[],thresholds:{strong:1,weak:-1},scoring_rules:{normalization:"raw"}});await load(active);}catch(e){setError(e instanceof Error?e.message:"Unable to create scorecard.");}};
  const evaluate=async()=>{if(!active||!snapshot?.scorecards[0]||!symbol.trim())return;try{setScoreResult(await evaluateResearchScorecard(active,snapshot.scorecards[0].id,symbol.trim()));}catch(e){setError(e instanceof Error?e.message:"Unable to evaluate scorecard.");}};
  const runCross=async()=>{if(!active)return;const symbols=crossAsset.split(",").map(s=>s.trim()).filter(Boolean);if(symbols.length<2){setError("Enter at least two comma-separated assets.");return;}try{await runCrossAssetResearch(active,symbols);await load(active);}catch(e){setError(e instanceof Error?e.message:"Unable to run cross-asset analysis.");}};
  const schedule=async()=>{if(!active)return;try{await createResearchAutomation(active,{name:"Daily Market Intelligence Brief",trigger_type:"SCHEDULE",schedule_cron:"0 7 * * *",condition:{timezone:"Africa/Lagos"},action:{type:"RESEARCH_RUN",query:"Market intelligence brief for workspace assets"},enabled:true});await load(active);}catch(e){setError(e instanceof Error?e.message:"Unable to schedule research.");}};

  return <div className="app"><main>
    <section className="hero"><div><div className="eyebrow">Phase 8 · Persistent research environment</div><h2>Research Workspaces</h2><p>Keep assets, dashboards, research runs, reports, alerts, watchpoints, scorecards and strategy experiments together.</p></div><div className="hero-stat"><BrainCircuit size={20}/><strong>{workspaces.length}</strong><span>workspaces</span></div></section>
    {error&&<div className="error"><AlertTriangle size={17}/>{error}</div>}
    <div className="ri-grid">
      <section className="panel"><div className="panel-head"><div><h3>Workspace library</h3><span>Create persistent research contexts by asset class, sector, strategy or theme.</span></div><button onClick={()=>void load()}><RefreshCw size={15}/> Refresh</button></div>
        <div className="ri-form"><input placeholder="Workspace name" value={name} onChange={e=>setName(e.target.value)}/><select value={type} onChange={e=>setType(e.target.value)}>{TYPES.map(x=><option key={x}>{x}</option>)}</select><button onClick={()=>void create()} disabled={busy}><Plus size={15}/> Create</button></div>
        {workspaces.map(w=><button key={w.id} className={`sidebar-item ${active===w.id?"active":""}`} onClick={()=>void load(w.id)}><span>{w.name}</span><small>{w.workspace_type}</small></button>)}
        {!workspaces.length&&<div className="settings-health-empty">No research workspaces yet.</div>}
      </section>
      <section className="panel"><div className="panel-head"><div><h3>{snapshot?.workspace.name??"Select a workspace"}</h3><span>{snapshot?.workspace.workspace_type??"Persistent research context"}</span></div></div>
        {snapshot&&<><div className="ri-form"><input placeholder="Add asset e.g. BTC/USD" value={symbol} onChange={e=>setSymbol(e.target.value)}/><button onClick={()=>void addAsset()}><Plus size={15}/> Add asset</button></div>
        <div className="quotes">{snapshot.assets.map(a=><div className="quote-row" key={a.id}><strong>{a.symbol}</strong><span>{a.role}</span></div>)}</div>
        <div className="panel-head"><div><h3>Custom dashboard</h3><span>Configurable widgets, layouts, saved views and custom metrics.</span></div><button onClick={()=>void createDashboard()}><BarChart3 size={15}/> Create default</button></div>
        <div className="quotes">{snapshot.dashboards.map(d=><div className="quote-row" key={d.id}><strong>{d.name}</strong><span>{(d.widgets??[]).length} widgets · {(d.saved_views??[]).length} saved views</span></div>)}</div>
        <div className="panel-head"><div><h3>Research automation</h3><span>Schedules plus event-driven rules.</span></div><button onClick={()=>void schedule()}><CalendarClock size={15}/> Daily 07:00</button></div>
        <div className="quotes">{snapshot.automation.map(a=><div className="quote-row" key={a.id}><strong>{a.name}</strong><span>{a.trigger_type} · {a.enabled?"enabled":"disabled"}</span></div>)}</div>
        <div className="panel-head"><div><h3>Custom scorecards</h3><span>Factors, weights, conditions and thresholds.</span></div><button onClick={()=>void createScore()}><Plus size={15}/> Create scorecard</button></div>
        <div className="quotes">{snapshot.scorecards.map(s=><div className="quote-row" key={s.id}><strong>{s.name}</strong><span>{(s.factors??[]).length} factors</span></div>)}</div>
        {snapshot.scorecards.length>0&&<div className="ri-form"><input placeholder="Asset to score" value={symbol} onChange={e=>setSymbol(e.target.value)}/><button onClick={()=>void evaluate()}>Evaluate</button></div>}
        {scoreResult&&<div className="auth-success">Score for {scoreResult.symbol}: <strong>{Number(scoreResult.score).toFixed(3)}</strong></div>}
        <div className="panel-head"><div><h3>Cross-asset research</h3><span>Correlation relationships are persisted with each run.</span></div></div>
        <div className="ri-form"><input placeholder="BTC/USD, ETH/USD, SPY" value={crossAsset} onChange={e=>setCrossAsset(e.target.value)}/><button onClick={()=>void runCross()}>Analyze</button></div>
        {snapshot.links.length===0&&snapshot.dashboards.length===0&&<div className="settings-health-empty">Start by adding assets and creating a dashboard.</div>}</>}
      </section>
    </div>
    <section className="panel"><div className="panel-head"><div><h3>Workspace continuity</h3><span>Research runs, reports, alerts, watchpoints and Quant Lab experiments can be attached to a workspace through persistent resource links.</span></div></div><p>AI Strategy Diagnosis is available from persisted Quant Lab experiments. It reports observed sample weakness, regime dependence and explicit evidence gaps; it does not infer performance decay or parameter instability without longitudinal data.</p></section>
    <footer>Phase 8 research automation is decision-support infrastructure. Scheduled and event-driven research produces persisted evidence; it does not execute trades autonomously.</footer>
  </main></div>;
}
