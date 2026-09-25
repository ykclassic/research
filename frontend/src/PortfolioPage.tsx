import { FormEvent, useCallback, useEffect, useState } from "react";
import { AlertTriangle, Plus, ShieldCheck, Trash2, X, RefreshCw } from "lucide-react";
import { ApiError, createPortfolioPosition, deletePortfolioPosition, getPortfolioIntelligence, getPortfolioSummary, runDefinedPortfolioScenario, User, PortfolioSummary, PortfolioIntelligence, PortfolioScenarioV2, PositionSide } from "./api";

const SYMBOLS = ["BTC/USD","ETH/USD","SOL/USD","EUR/USD","GBP/USD","USD/JPY","NVDA","AAPL","MSFT","SPY"];
const ASSET_CLASSES = ["CRYPTO","FOREX","STOCK","ETF","OTHER"];

function pct(v:number|null|undefined){return v==null?"—":v.toFixed(1)+"%";}
function num(v:number|null|undefined){return v==null?"—":v.toLocaleString(undefined,{maximumFractionDigits:2});}
function Bars({items}:{items:Record<string,number>}){return <div className="metadata">{Object.entries(items).sort((a,b)=>b[1]-a[1]).map(([k,v])=><div key={k}><span>{k}</span><strong>{pct(v)}</strong></div>)}</div>;}

export default function PortfolioPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: any) => void }) {
  const [summary,setSummary]=useState<PortfolioSummary|null>(null);
  const [intel,setIntel]=useState<PortfolioIntelligence|null>(null);
  const [loading,setLoading]=useState(true);
  const [refreshing,setRefreshing]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [showAdd,setShowAdd]=useState(false);
  const [symbol,setSymbol]=useState(SYMBOLS[0]);
  const [side,setSide]=useState<PositionSide>("LONG");
  const [quantity,setQuantity]=useState("");
  const [entry,setEntry]=useState("");
  const [assetClass,setAssetClass]=useState("OTHER");
  const [sector,setSector]=useState("OTHER");
  const [category,setCategory]=useState("OTHER");
  const [scenarioType,setScenarioType]=useState("ASSET_SHOCK");
  const [scenarioSymbol,setScenarioSymbol]=useState(SYMBOLS[0]);
  const [scenarioPct,setScenarioPct]=useState("-15");
  const [scenario,setScenario]=useState<PortfolioScenarioV2|null>(null);
  const [busy,setBusy]=useState(false);

  const load=useCallback(async(force=false)=>{
    try{setError(null);if(force)setRefreshing(true);const [s,i]=await Promise.all([getPortfolioSummary(),getPortfolioIntelligence()]);setSummary(s);setIntel(i);}
    catch(e){if(e instanceof ApiError&&e.status===401){onLogout();return;}setError(e instanceof Error?e.message:"Unable to load portfolio intelligence.");}
    finally{setLoading(false);setRefreshing(false);}
  },[onLogout]);
  useEffect(()=>{void load();},[load]);

  const add=async(e:FormEvent)=>{e.preventDefault();setBusy(true);try{await createPortfolioPosition({symbol,side,quantity:Number(quantity),average_entry_price:Number(entry),asset_class:assetClass,sector,category});setQuantity("");setEntry("");setShowAdd(false);await load(true);}catch(x){setError(x instanceof Error?x.message:"Unable to add position.");}finally{setBusy(false);}};
  const remove=async(id:string)=>{if(!window.confirm("Remove this portfolio position?"))return;try{await deletePortfolioPosition(id);await load(true);}catch(x){setError(x instanceof Error?x.message:"Unable to remove position.");}};
  const runScenario=async()=>{try{setScenario(await runDefinedPortfolioScenario({scenario_type:scenarioType,symbol:scenarioType==="ASSET_SHOCK"?scenarioSymbol:undefined,shock_percent:scenarioType==="ASSET_SHOCK"?Number(scenarioPct):0}));}catch(x){setError(x instanceof Error?x.message:"Unable to run scenario.");}};

  return <div className="app">
    <header className="topbar"><div><div className="eyebrow">Phase 7 · Portfolio Intelligence</div><h1>Portfolio & Decision Support</h1></div><nav className="main-nav"><button className="nav-button" onClick={()=>setPage("market")}>Market Data</button><button className="nav-button" onClick={()=>setPage("analysis")}>Technical Analysis</button><button className="nav-button" onClick={()=>setPage("signals")}>Signals</button><button className="nav-button active">Portfolio</button><button className="nav-button" onClick={()=>setPage("quant-lab")}>Quant Lab</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header>
    <main>
      <section className="hero"><div><div className="eyebrow">Decision support</div><h2>Understand what drives portfolio risk—not just where balances sit.</h2><p>Exposure, concentration, correlation, risk contribution, regimes, signals and defined scenarios are descriptive analytics, not forecasts.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>{summary?.position_count??0}</strong><span>positions tracked</span></div></section>
      {error&&<div className="error"><AlertTriangle size={17}/>{error}</div>}
      {loading?<div className="empty">Loading portfolio intelligence…</div>:<>
        <div className="panel-head"><div><h3>Portfolio risk snapshot</h3><span>Calculated from validated quotes and completed daily candles where available.</span></div><button className="refresh" onClick={()=>void load(true)} disabled={refreshing}><RefreshCw size={15}/>{refreshing?"Refreshing":"Refresh intelligence"}</button></div>
        <section className="metadata portfolio-metrics"><div><span>Gross exposure</span><strong>{num(summary?.gross_exposure)}</strong></div><div><span>Net exposure</span><strong>{num(summary?.net_exposure)}</strong></div><div><span>Unrealized P&amp;L</span><strong>{num(summary?.unrealized_pnl)}</strong></div><div><span>Max concentration</span><strong>{pct(summary?.max_position_concentration_percent)}</strong></div><div><span>Risk flags</span><strong>{intel?.alerts.length??0}</strong></div></section>

        <section className="workspace-grid">
          <section className="panel"><div className="panel-head"><div><h3>Holdings</h3><span>Classification drives allocation and concentration analysis.</span></div><button className="icon-button" aria-label="Add position" onClick={()=>setShowAdd(true)}><Plus size={17}/></button></div>
            {showAdd&&<form className="inline-form" onSubmit={add}><select value={symbol} onChange={e=>setSymbol(e.target.value)}>{SYMBOLS.map(s=><option key={s}>{s}</option>)}</select><select value={side} onChange={e=>setSide(e.target.value as PositionSide)}><option>LONG</option><option>SHORT</option></select><input aria-label="Quantity" type="number" step="any" min="0.00000001" placeholder="Quantity" value={quantity} onChange={e=>setQuantity(e.target.value)} required/><input aria-label="Entry price" type="number" step="any" min="0.00000001" placeholder="Entry" value={entry} onChange={e=>setEntry(e.target.value)} required/><select aria-label="Asset class" value={assetClass} onChange={e=>setAssetClass(e.target.value)}>{ASSET_CLASSES.map(s=><option key={s}>{s}</option>)}</select><input aria-label="Sector" placeholder="Sector" value={sector} onChange={e=>setSector(e.target.value)}/><input aria-label="Category" placeholder="Category" value={category} onChange={e=>setCategory(e.target.value)}/><button type="submit" disabled={busy}>Add</button><button type="button" className="icon-button" onClick={()=>setShowAdd(false)}><X size={15}/></button></form>}
            {summary?.positions.length?<div className="quotes">{summary.positions.map(p=><div className="quote-row" key={p.position.id}><div className="symbol">{p.position.symbol}</div><div className="price">{num(p.current_price)}</div><div className="status">{p.position.side}</div><div className="timestamp">{p.position.asset_class} · {p.position.sector} · {pct(intel?.exposures.find(e=>e.symbol===p.position.symbol)?.weight_percent)}</div><button className="icon-button danger" aria-label={`Remove ${p.position.symbol}`} onClick={()=>void remove(p.position.id)}><Trash2 size={14}/></button></div>)}</div>:<div className="empty">No positions yet. Add a position to begin analysis.</div>}
          </section>
          <section className="panel"><div className="panel-head"><div><h3>Scenario engine</h3><span>Defined assumptions; no prediction is implied.</span></div></div><div className="inline-form"><select value={scenarioType} onChange={e=>setScenarioType(e.target.value)}><option value="ASSET_SHOCK">Asset shock</option><option value="USD_STRENGTHENS">USD strengthens</option><option value="HIGH_VOLATILITY">High-volatility regime</option></select>{scenarioType==="ASSET_SHOCK"&&<><select value={scenarioSymbol} onChange={e=>setScenarioSymbol(e.target.value)}>{SYMBOLS.map(s=><option key={s}>{s}</option>)}</select><input type="number" step="0.5" value={scenarioPct} onChange={e=>setScenarioPct(e.target.value)} aria-label="Shock percent"/><span>%</span></>}<button onClick={()=>void runScenario()}>Run</button></div>{scenario&&<div className="metadata"><div><span>P&amp;L delta</span><strong>{num(scenario.projected_pnl_delta)}</strong></div><div><span>Projected P&amp;L</span><strong>{num(scenario.projected_unrealized_pnl)}</strong></div><div><span>Gross exposure</span><strong>{num(scenario.projected_gross_exposure)}</strong></div><div><span>Affected</span><strong>{scenario.affected_positions}</strong></div></div>}{scenario&&<div className="eligibility"><ShieldCheck size={16}/><div><strong>{scenario.name}</strong>{scenario.assumptions.map(a=><span key={a}>{a}</span>)}{scenario.data_quality.map(a=><span key={a}>{a}</span>)}</div></div>}</section>
        </section>

        {intel&&<><section className="workspace-grid"><section className="panel"><div className="panel-head"><div><h3>Asset allocation</h3><span>Gross exposure by asset class.</span></div></div><Bars items={intel.asset_allocation}/></section><section className="panel"><div className="panel-head"><div><h3>Sector / category exposure</h3><span>Classification-based concentration.</span></div></div><Bars items={intel.sector_exposure}/><Bars items={intel.category_exposure}/></section></section>
        <section className="panel"><div className="panel-head"><div><h3>Correlation & clusters</h3><span>Daily-return correlations where at least 20 observations are available.</span></div></div>{intel.correlation_clusters.map(c=><div className="quote-row" key={c.cluster_id}><div className="symbol">{c.cluster_id}</div><div>{c.symbols.join(" · ")}</div><div className="timestamp">{c.average_pairwise_correlation==null?"Insufficient sample":c.average_pairwise_correlation.toFixed(2)} avg correlation</div></div>)}{!intel.correlation_clusters.length&&<div className="empty">No correlation clusters available.</div>}</section>
        <section className="workspace-grid"><section className="panel"><div className="panel-head"><div><h3>Risk contribution</h3><span>Exposure × annualized daily volatility proxy.</span></div></div>{intel.risk_contribution.map(r=><div className="quote-row" key={r.symbol}><div className="symbol">{r.symbol}</div><div>Exposure {pct(r.exposure_percent)}</div><div>Vol {pct(r.volatility_percent)}</div><div className="timestamp">Risk {pct(r.risk_contribution_percent)}</div></div>)}</section><section className="panel"><div className="panel-head"><div><h3>Regime & signal exposure</h3><span>Current descriptive context by holding.</span></div></div>{intel.regime_alignment.map(r=><div className="quote-row" key={r.symbol}><div className="symbol">{r.symbol}</div><div>{r.regime}</div><div>Confidence {pct(r.confidence*100)}</div><div className="timestamp">{intel.signal_exposure.find(s=>s.symbol===r.symbol)?.active_signals??0} active signals</div></div>)}</section></section>
        {Boolean(intel.alerts.length||intel.risk_drivers.length||intel.changes.length)&&<section className="panel warning"><AlertTriangle size={16}/><div><strong>Portfolio intelligence</strong>{intel.alerts.map(x=><span key={x}>{x}</span>)}{intel.risk_drivers.map(x=><span key={x}>{x}</span>)}{intel.changes.map(x=><span key={x}>{x}</span>)}</div></section>}
        {(intel.relevant_signals.length||intel.relevant_catalysts.length)&&<section className="workspace-grid"><section className="panel"><div className="panel-head"><h3>Relevant signals</h3></div>{intel.relevant_signals.map(x=><div className="quote-row" key={x}>{x}</div>)}</section><section className="panel"><div className="panel-head"><h3>Relevant catalysts</h3></div>{intel.relevant_catalysts.map(x=><div className="quote-row" key={x}>{x}</div>)}</section></section>}
        {Boolean(intel.data_quality.length)&&<section className="panel"><div className="panel-head"><h3>Data quality</h3></div>{intel.data_quality.map(x=><div className="timestamp" key={x}>{x}</div>)}</section>}
        </>}
        <footer>Research and decision support only. Scenario outputs are deterministic estimates under stated assumptions and do not establish future performance.</footer>
      </>}
    </main>
  </div>;
}
