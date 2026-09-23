import { useCallback, useEffect, useState } from "react";
import { Check, CreditCard, Gauge, RefreshCw, Sparkles } from "lucide-react";
import type { User } from "./api";
import { getBillingHistory, getBillingPlans, getEntitlements, getSubscription, getUsage, startProTrial, startCheckout, changePlan, reconcileCheckout, cancelSubscription, resumeSubscription, type BillingEvent, type BillingPlan, type BillingSubscription, type EntitlementSnapshot, type UsageSummary } from "./billingApi";

type Props={user:User;onLogout:()=>void};
const labels:Record<string,string>={core_research:"Core market research",watchlists:"Watchlists",basic_portfolio:"Basic portfolio",signal_intelligence:"Signal intelligence",ai_research:"AI research",advanced_portfolio_analytics:"Advanced portfolio analytics",backtesting:"Backtesting",strategy_builder:"Strategy builder",scanner:"Intelligent scanner",webhooks:"Webhooks",scheduled_workflows:"Scheduled workflows",api:"API access",mcp:"MCP access",exports:"Advanced exports",team_workspaces:"Team workspaces"};
const freeFeatures=new Set(["core_research","watchlists","basic_portfolio","signal_intelligence","ai_research"]);
const money=(minor:number,currency:string)=>minor===0?"Free":currency+" "+(minor/100).toFixed(2)+"/month";

export default function BillingPage({user,onLogout}:Props){
 const [plans,setPlans]=useState<BillingPlan[]>([]),[ent,setEnt]=useState<EntitlementSnapshot|null>(null),[sub,setSub]=useState<BillingSubscription|null>(null),[usage,setUsage]=useState<UsageSummary|null>(null),[history,setHistory]=useState<BillingEvent[]>([]),[billingTestMode,setBillingTestMode]=useState(false),[busy,setBusy]=useState(false),[billingSyncing,setBillingSyncing]=useState(false),[error,setError]=useState<string|null>(null);

 const load=useCallback(async()=>{try{setError(null);const[p,e,s,u,h]=await Promise.all([getBillingPlans(),getEntitlements(),getSubscription(),getUsage(),getBillingHistory()]);setPlans(p.plans);setBillingTestMode(p.billing_test_mode);setEnt(e);setSub(s.subscription);setUsage(u);setHistory(h.events)}catch(e){if(e instanceof Error&&/authentication|required/i.test(e.message)){onLogout();return}setError(e instanceof Error?e.message:"Unable to load billing.")}},[onLogout]);

 useEffect(()=>{
  const params=new URLSearchParams(window.location.search);
  const billing=params.get("billing");
  const sessionId=params.get("session_id");
  let cancelled=false;
  let timer:number|undefined;
  const initialize=async()=>{
   if(billing!=="success"){
    await load();
    return;
   }
   if(!sessionId){
    setError("Stripe returned a successful payment without a Checkout session ID. The subscription was not synchronized.");
    await load();
    return;
   }
   setBillingSyncing(true);
   setError(null);
   for(let attempt=1;attempt<=6&&!cancelled;attempt+=1){
    try{
     await reconcileCheckout(sessionId);
     await load();
     if(!cancelled){
      setBillingSyncing(false);
      window.history.replaceState({},document.title,window.location.pathname);
     }
     return;
    }catch(e){
     if(attempt===6){
      if(!cancelled){
       setBillingSyncing(false);
       setError(e instanceof Error?e.message:"Unable to synchronize the Stripe subscription.");
      }
      return;
     }
     await new Promise<void>(resolve=>{timer=window.setTimeout(resolve,1500)});
    }
   }
  };
  void initialize();
  return()=>{cancelled=true;if(timer!==undefined)window.clearTimeout(timer)};
 },[load]);

 const checkout=async(planId:string)=>{setBusy(true);setError(null);try{const result=await startCheckout(planId);window.location.assign(result.checkout_url)}catch(e){setError(e instanceof Error?e.message:"Unable to start checkout.");setBusy(false)}};
 const change=async(planId:string)=>{setBusy(true);setError(null);try{const result=await changePlan(planId);if(result.checkout_url){window.location.assign(result.checkout_url);return}await load()}catch(e){setError(e instanceof Error?e.message:"Unable to change plan.")}finally{setBusy(false)}};
 const cancel=async()=>{setBusy(true);setError(null);try{await cancelSubscription(true);await load()}catch(e){setError(e instanceof Error?e.message:"Unable to cancel subscription.")}finally{setBusy(false)}};
 const resume=async()=>{setBusy(true);setError(null);try{await resumeSubscription();await load()}catch(e){setError(e instanceof Error?e.message:"Unable to resume subscription.")}finally{setBusy(false)}};
 const trial=async()=>{setBusy(true);setError(null);try{await startProTrial();await load()}catch(e){setError(e instanceof Error?e.message:"Unable to start trial.")}finally{setBusy(false)}};

 return <div className="app billing-app"><main>
  <section className="billing-hero"><div><div className="eyebrow">Commercial infrastructure · Phase 1</div><h2>Plans, entitlements and usage.</h2><p>Your plan is resolved on the backend and usage limits are enforced before metered work executes.</p></div><div className="billing-status"><CreditCard size={18}/><strong>{ent?.plan.name??"Free"}</strong><span>{sub?.status??"free"}</span></div></section>
  {billingSyncing&&<div className="billing-test-banner"><strong>Payment received</strong><span>Stripe Checkout session received. Synchronizing your subscription and entitlements…</span></div>}
  {billingTestMode&&<div className="billing-test-banner"><strong>Billing test mode</strong><span>Plan switches are instant and do not create real charges. The production Stripe integration remains unchanged.</span></div>}{error&&<div className="billing-error">{error}</div>}
  <section className="billing-section"><div className="billing-section-head"><div><h3>Pricing</h3><span>Capabilities come from the centralized entitlement model.</span></div><button onClick={()=>void load()} disabled={busy}><RefreshCw size={15}/>Refresh</button></div>
   <div className="billing-plans">{plans.map(plan=><article className={"billing-plan "+(plan.id===ent?.plan_id?"current":"")} key={plan.id}><div className="billing-plan-top"><div><span className="billing-plan-kicker">{plan.id==="premium"?"Professional":plan.name}</span><h4>{plan.name}</h4></div>{plan.id===ent?.plan_id&&<span className="billing-current">Current</span>}</div><strong className="billing-price">{money(plan.monthly_price_minor,plan.currency)}</strong><p>{plan.description}</p>{plan.id==="pro"&&!sub&&!billingTestMode&&<button className="billing-primary" onClick={()=>void trial()} disabled={busy}><Sparkles size={15}/>{busy?"Starting…":"Start 14-day Pro trial"}</button>}{billingTestMode&&plan.id!==ent?.plan_id&&<button className="billing-primary" onClick={()=>void change(plan.id)} disabled={busy}>Switch to {plan.name}</button>}{!billingTestMode&&plan.id!=="free"&&plan.id!==ent?.plan_id&&sub&&<button className="billing-primary" onClick={()=>void change(plan.id)} disabled={busy}>Switch to {plan.name}</button>}{!billingTestMode&&plan.id!=="free"&&!sub&&<button className="billing-primary" onClick={()=>void checkout(plan.id)} disabled={busy}>Subscribe to {plan.name}</button>}<ul>{Object.entries(labels).map(([key,label])=><li key={key} className={(freeFeatures.has(key)||plan.id!=="free")?"included":""}><Check size={14}/>{label}</li>)}</ul></article>)}</div>
  </section>
  <section className="billing-grid"><article className="billing-section"><div className="billing-section-head"><div><h3>Subscription</h3><span>Provider-neutral subscription state.</span></div></div><div className="billing-card"><div><strong>{ent?.plan.name??"Free"}</strong><p>Status: {sub?.status??"free"}</p></div>{sub?.trial_ends_at&&<div><span>Trial ends</span><strong>{new Date(sub.trial_ends_at).toLocaleDateString()}</strong></div>}<small>Checkout, renewal, cancellation and invoices are synchronized through the configured billing provider.</small>{sub?.cancel_at_period_end?<button className="billing-primary" onClick={()=>void resume()} disabled={busy}>Resume subscription</button>:sub&&sub.status!=="canceled"?<button className="billing-secondary" onClick={()=>void cancel()} disabled={busy}>Cancel at period end</button>:null}</div></article>
  <article className="billing-section"><div className="billing-section-head"><div><h3>Usage</h3><span>Current UTC billing period.</span></div><Gauge size={18}/></div><div className="usage-list">{usage?.notifications?.length?<div className="billing-card"><strong>Usage alerts</strong>{usage.notifications.map(n=><div className="billing-event" key={`${n.metric}-${n.threshold_percent}`}><span>{n.metric.replaceAll("_"," ")}</span><strong>{n.threshold_percent}% used</strong><time>{new Date(n.created_at).toLocaleString()}</time></div>)}</div>:null}{usage&&Object.entries(usage.metrics).map(([metric,m])=>{const pct=m.limit===-1?8:Math.min(100,(m.used/Math.max(1,m.limit))*100);return <div className="usage-row" key={metric}><div><strong>{metric.replaceAll("_"," ")}</strong><span>{m.limit===-1?"Unlimited":m.used+" / "+m.limit}</span></div><div className="usage-track"><i style={{width:pct+"%"}}/></div></div>})}</div></article></section>
  <section className="billing-section"><div className="billing-section-head"><div><h3>Billing history</h3><span>Provider events retained for auditability.</span></div></div>{history.length===0?<div className="billing-empty">No billing events yet.</div>:history.map(event=><div className="billing-event" key={event.id}><strong>{event.event_type}</strong><span>{event.provider}</span><time>{new Date(event.created_at).toLocaleString()}</time></div>)}</section>
  <footer>Research and decision support only. Billing access never bypasses market-data validation or analytical safeguards.</footer>
 </main></div>;
}
