import { useState } from "react";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { ApiError, User } from "./api";

type Props={user:User;onLogout:()=>void;setPage:(p:any)=>void};

export default function QuantLabPage({user,onLogout,setPage}:Props){
 const [symbol,setSymbol]=useState("BTC/USD"),[threshold,setThreshold]=useState("0"),[result,setResult]=useState<any>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
 const run=async()=>{
  setBusy(true);setError(null);
  try{
   const csrf=document.cookie.match(/(?:^|; )mr_csrf_token=([^;]+)/)?.[1]??"";
   const now=Date.now(), day=86400000;
   const candles=Array.from({length:10},(_,i)=>{const p=100+i;return {timestamp:new Date(now-(10-i)*day).toISOString(),open:p,high:p+2,low:p-2,close:p+1,volume:1000,symbol,timeframe:"1d",source:"research-ui",is_complete:true};});
   const body={strategy:{name:"Close threshold",version:1,direction:"LONG",timeframe:"1d",entry_rules:[{field:"close",operator:"gt",value:Number(threshold)}],exit_rules:[{field:"close",operator:"gt",value:Number(threshold)+2}]},dataset:{symbol,timeframe:"1d",source:"research-ui",requested_at:new Date().toISOString(),candles},experiment:{dataset_version:"ui-demo-v1",strategy_version:"close-threshold-v1",feature_version:"feature-set-v1",parameters:{threshold:Number(threshold)},costs:{},execution:{commission_bps:5,slippage_bps:2,spread_bps:2,position_size:1},train_start:new Date(now-9*day).toISOString(),train_end:new Date(now-6*day).toISOString(),validation_start:new Date(now-6*day).toISOString(),validation_end:new Date(now-3*day).toISOString(),test_start:new Date(now-3*day).toISOString(),test_end:new Date(now).toISOString()}};
   const r=await fetch("/api/quant-lab/backtests",{method:"POST",credentials:"include",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(body)});
   if(!r.ok)throw new ApiError((await r.json()).detail??"Backtest failed.",r.status);
   setResult(await r.json());
  }catch(e){if(e instanceof ApiError&&e.status===401){onLogout();return;}setError(e instanceof Error?e.message:"Unable to run backtest.");}finally{setBusy(false);}
 };
 return <div className="app"><header className="topbar"><div className="product-brand"><div><div className="eyebrow">Phase 6 · Quant Lab</div><h1>Quant Lab</h1></div></div><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header><main>
 <section className="hero"><div><div className="eyebrow">Observation → Hypothesis → Test → Validation → Paper Trading</div><h2>Systematic strategy research.</h2><p>Backtests are research experiments, not forecasts or guarantees of future performance.</p></div><FlaskConical size={32}/></section>
 {error&&<div className="error"><AlertTriangle size={17}/>{error}</div>}
 <section className="panel"><div className="panel-head"><div><h3>Strategy Builder</h3><span>Rule-based foundation with versioned experiment assumptions.</span></div></div><div className="inline-form"><label>Asset<input value={symbol} onChange={e=>setSymbol(e.target.value)}/></label><label>Entry close &gt;<input type="number" value={threshold} onChange={e=>setThreshold(e.target.value)}/></label><button onClick={()=>void run()} disabled={busy}>{busy?"Running…":"Run backtest"}</button></div></section>
 {result&&<section className="workspace-grid"><div className="panel"><h3>Backtest metrics</h3><div className="quotes">{Object.entries(result.metrics).filter(([k])=>!["regime_breakdown","timeframe_breakdown","r_distribution"].includes(k)).map(([k,v])=><div className="quote-row" key={k}><span>{k.replaceAll("_"," ")}</span><strong>{typeof v==="number"?Number(v).toFixed(4):String(v??"—")}</strong></div>)}</div></div><div className="panel"><h3>Validation controls</h3>{Object.entries(result.anti_overfit_checks).map(([k,v])=><div className="quote-row" key={k}><span>{k.replaceAll("_"," ")}</span><strong>{v?"PASS":"FAIL"}</strong></div>)}</div></section>}
 <footer>Research and decision support only. No autonomous real-money trading.</footer></main></div>;
}
