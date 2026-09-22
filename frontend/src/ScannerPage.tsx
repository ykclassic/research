import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Bell, Check, Play, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import type { AppPage } from "./App";
import { ApiError, createScannerPreset, createScannerSchedule, deleteScannerPreset, deleteScannerSchedule, getScannerAlerts, getScannerOpportunities, getScannerPresets, getScannerSchedules, markScannerAlertRead, runScanner, ScannerAlert, ScannerOpportunity, ScannerPreset, ScannerSchedule, ScannerConditionRule } from "./api";
import { getMarketUniverse, MarketUniverse } from "./settingsApi";

const ALERT_EVENTS = ["NEW_QUALIFIED_SIGNAL","SIGNAL_UPGRADE","SIGNAL_DOWNGRADE","REGIME_CHANGE","BOS_CHOCH","LIQUIDITY_SWEEP","SETUP_FORMATION","TARGET_REACHED","INVALIDATION","VOLATILITY_REGIME_CHANGE","RESEARCH_DIVERGENCE","WATCHPOINT"];

function pct(value:number|null|undefined):string{return value==null?"—":`${Math.round(value*100)}%`;}
function rr(value:number|null|undefined):string{return value==null?"—":value.toFixed(2);}
function time(value:string):string{return new Date(value).toLocaleString([], {dateStyle:"medium",timeStyle:"short"});}

export default function ScannerPage({user,onLogout,setPage}:{user:{email:string};onLogout:()=>void;setPage:(p:AppPage)=>void}){
  const [presets,setPresets]=useState<ScannerPreset[]>([]);
  const [opportunities,setOpportunities]=useState<ScannerOpportunity[]>([]);
  const [alerts,setAlerts]=useState<ScannerAlert[]>([]);
  const [schedules,setSchedules]=useState<ScannerSchedule[]>([]);
  const [universe,setUniverse]=useState<MarketUniverse|null>(null);
  const [active,setActive]=useState<string>("");
  const [name,setName]=useState("High-confidence crypto");
  const [minConfidence,setMinConfidence]=useState("0.82");
  const [minRR,setMinRR]=useState("1.5");
  const [minAlignment,setMinAlignment]=useState("3");
  const [interval,setIntervalValue]=useState("60");
  const [timeframes,setTimeframes]=useState(["15m","1h","4h","1D"]);
  const [customField,setCustomField]=useState("confidence");
  const [customOperator,setCustomOperator]=useState("gte");
  const [customValue,setCustomValue]=useState("0.9");
  const [customConditions,setCustomConditions]=useState<Array<{field:string;operator:string;value:string}>>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");

  const load=useCallback(async()=>{
    try{
      const [p,o,a,s,u]=await Promise.all([getScannerPresets(),getScannerOpportunities(),getScannerAlerts(),getScannerSchedules(),getMarketUniverse()]);
      setPresets(p);setOpportunities(o);setAlerts(a);setSchedules(s);setUniverse(u);setActive(cur=>p.some(x=>x.id===cur)?cur:p[0]?.id??"");setError("");
    }catch(e){if(e instanceof ApiError&&e.status===401){onLogout();return;}setError(e instanceof Error?e.message:"Unable to load scanner.");}
  },[onLogout]);
  useEffect(()=>{void load();},[load]);

  const create=async()=>{
    if(!universe||!name.trim())return;
    setBusy(true);
    try{
      const symbols=universe.enabled_symbols.slice(0,20);
      const created=await createScannerPreset({
        name:name.trim(),description:"Deterministic multi-factor opportunity scanner.",
        asset_universe:symbols,timeframes,
        conditions:{min_confidence:Number(minConfidence),min_risk_reward:Number(minRR),regimes:[],directions:["BUY","STRONG_BUY","SELL","STRONG_SELL"],structures:[],min_mtf_alignment:Number(minAlignment),require_qualified:true,custom_match:"ALL",custom_conditions:customConditions.map(item=>({field:item.field,operator:item.operator,value:Number.isNaN(Number(item.value))?item.value:Number(item.value)})) as ScannerConditionRule[]},
        alert_events:["NEW_QUALIFIED_SIGNAL","SIGNAL_UPGRADE","REGIME_CHANGE","BOS_CHOCH","LIQUIDITY_SWEEP","SETUP_FORMATION","TARGET_REACHED","INVALIDATION","RESEARCH_DIVERGENCE"]
      });
      setActive(created.id);await load();
    }catch(e){setError(e instanceof Error?e.message:"Unable to create scanner.");}finally{setBusy(false);}
  };
  const scan=async(id:string)=>{setBusy(true);try{await runScanner(id);await load();}catch(e){setError(e instanceof Error?e.message:"Scanner run failed.");}finally{setBusy(false);}};
  const remove=async(id:string)=>{try{await deleteScannerPreset(id);await load();}catch(e){setError(e instanceof Error?e.message:"Unable to delete scanner.");}};
  const schedule=async()=>{if(!active)return;try{await createScannerSchedule({preset_id:active,name:"Scanner schedule",interval_minutes:Number(interval)});await load();}catch(e){setError(e instanceof Error?e.message:"Unable to schedule scanner.");}};
  const removeSchedule=async(id:string)=>{try{await deleteScannerSchedule(id);await load();}catch(e){setError(e instanceof Error?e.message:"Unable to delete schedule.");}};
  const readAlert=async(id:string)=>{try{const item=await markScannerAlertRead(id);setAlerts(current=>current.map(a=>a.id===id?item:a));}catch(e){setError(e instanceof Error?e.message:"Unable to mark alert read.");}};

  return <div className="app">
    <header className="topbar"><div><div className="eyebrow">Phase 3 · Continuous intelligence</div><h1>Market Scanner</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button active">Scanner</button><button className="nav-button" onClick={()=>setPage("signals")}>Signals</button><button className="nav-button" onClick={()=>setPage("signal-intelligence")}>Signal Intelligence</button><button className="nav-button" onClick={()=>setPage("alerts")}>Alerts</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header>
    <main>
      <section className="hero"><div><div className="eyebrow">Opportunity discovery</div><h2>Let the system watch the configured market universe.</h2><p>Every opportunity is shown with its underlying evidence. The board does not present an arbitrary “best trade” ranking.</p></div><div className="hero-stat"><Search size={20}/><strong>{opportunities.length}</strong><span>qualified opportunities</span></div></section>
      {error&&<div className="error" role="alert"><AlertTriangle size={17}/>{error}</div>}
      <section className="workspace-grid">
        <aside className="panel">
          <div className="panel-head"><div><h3>Saved scanners</h3><span>{presets.length} presets</span></div><RefreshCw size={16}/></div>
          <label>Name<input value={name} onChange={e=>setName(e.target.value)}/></label>
          <label>Minimum confidence<input type="number" min="0" max="1" step="0.01" value={minConfidence} onChange={e=>setMinConfidence(e.target.value)}/></label>
          <label>Minimum RR<input type="number" min="0" step="0.1" value={minRR} onChange={e=>setMinRR(e.target.value)}/></label>
          <label>Minimum MTF alignment<input type="number" min="0" max="4" value={minAlignment} onChange={e=>setMinAlignment(e.target.value)}/></label>
          <fieldset><legend>Scan timeframes</legend><div className="settings-toggle-grid">{["15m","1h","4h","1D"].map(tf=><label key={tf}><input type="checkbox" checked={timeframes.includes(tf)} onChange={e=>setTimeframes(v=>e.target.checked?[...v,tf]:v.filter(x=>x!==tf))}/>{tf}</label>)}</div></fieldset>
          <fieldset><legend>Custom conditions</legend><div className="inline-form"><select value={customField} onChange={e=>setCustomField(e.target.value)}><option value="confidence">Confidence</option><option value="risk_reward">RR</option><option value="mtf_alignment">MTF alignment</option><option value="momentum">Momentum</option><option value="volatility">Volatility</option><option value="volume">Volume</option><option value="trend">Trend</option><option value="direction">Direction</option><option value="regime">Regime</option><option value="structure">Structure</option><option value="liquidity">Liquidity</option></select><select value={customOperator} onChange={e=>setCustomOperator(e.target.value)}><option value="gte">≥</option><option value="lte">≤</option><option value="eq">=</option><option value="contains">contains</option></select><input value={customValue} onChange={e=>setCustomValue(e.target.value)} placeholder="Value"/><button type="button" onClick={()=>{if(customValue.trim())setCustomConditions(v=>[...v,{field:customField,operator:customOperator,value:customValue}]);}}>Add</button></div>{customConditions.map((x,i)=><small key={i}>{x.field} {x.operator} {x.value}</small>)}</fieldset>
          <button className="primary-button" onClick={()=>void create()} disabled={busy||!universe?.enabled_symbols.length}><Plus size={15}/>Create scanner</button>
          <div className="rules-list">{presets.map(p=><div className={`rule-row ${active===p.id?"selected":""}`} key={p.id}><button className="watchlist-select" onClick={()=>setActive(p.id)}><strong>{p.name}</strong><small>{p.asset_universe.length} assets · ≥ {pct(p.conditions.min_confidence)} · RR {rr(p.conditions.min_risk_reward)}</small></button><button className="icon-button danger" onClick={()=>void remove(p.id)} aria-label={`Delete ${p.name}`}><Trash2 size={14}/></button></div>)}</div>
          {active&&<div className="inline-form"><input type="number" min="15" max="10080" value={interval} onChange={e=>setIntervalValue(e.target.value)}/><button onClick={()=>void schedule()}><Plus size={14}/>Schedule minutes</button></div>}
          {schedules.map(s=><div className="quote-row" key={s.id}><span>{s.name} · every {s.interval_minutes}m</span><button className="icon-button danger" onClick={()=>void removeSchedule(s.id)}><Trash2 size={14}/></button></div>)}
        </aside>
        <section className="panel">
          <div className="panel-head"><div><h3>Opportunity Board</h3><span>Structured discovery · no arbitrary ranking</span></div>{active&&<button className="refresh" onClick={()=>void scan(active)} disabled={busy}><Play size={15}/>{busy?"Scanning…":"Run scan"}</button>}</div>
          {opportunities.length===0?<div className="settings-health-empty">No qualified opportunities have been produced by the saved scanners yet.</div>:
          <div className="intel-table"><div className="intel-row intel-head"><span>Asset / Setup</span><span>Regime</span><span>Direction</span><span>Confidence</span><span>RR</span><span>Structure</span><span>Evidence</span></div>
          {opportunities.map(o=><div className="intel-row" key={o.id??o.signal_id}><span><strong>{o.symbol}</strong><small>{o.setup}</small></span><span>{o.regime??"—"}</span><span>{o.direction}</span><span>{pct(o.confidence)}</span><span>{rr(o.risk_reward)}</span><span>{o.structure??"—"}</span><span>{o.historical_evidence.sample_size ? `${String(o.historical_evidence.sample_size)} samples` : "No history"}</span></div>)}</div>}
        </section>
      </section>
      <section className="workspace-grid">
        <section className="panel"><div className="panel-head"><div><h3>Intelligent alerts</h3><span>Event-driven, deduplicated scanner notifications</span></div><Bell size={17}/></div>{alerts.length===0?<div className="settings-health-empty">No scanner events yet.</div>:alerts.slice(0,20).map(a=><div className={`event-row ${a.read_at?"read":"unread"}`} key={a.id}><div className="event-dot"/><div><strong>{a.title} · {a.symbol}</strong><p>{a.message}</p><small>{a.event_type} · {time(a.triggered_at)}</small>{!a.read_at&&<button className="read-button" onClick={()=>void readAlert(a.id)}><Check size={13}/> Mark read</button>}</div></div>)}</section>
        <section className="panel"><div className="panel-head"><div><h3>Alert policy</h3><span>Signal quality over notification volume</span></div></div><p>Scanner alerts are generated only from saved conditions and state transitions. Historical evidence is descriptive and is suppressed as meaningful when the matching sample is below the configured minimum.</p><ul><li>No “best trade” score.</li><li>No execution authorization.</li><li>Completed-candle market evidence only.</li><li>Deduplicated event fingerprints.</li></ul></section>
      </section>
      <footer>Research and decision support only. No autonomous trading.</footer>
    </main>
  </div>;
}
