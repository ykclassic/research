export interface BillingPlan { id:string; name:string; description:string; monthly_price_minor:number; currency:string; display_order:number; active:boolean; }
export interface BillingSubscription { id:string; user_id:string; plan_id:string; status:"trialing"|"active"|"past_due"|"unpaid"|"paused"|"canceled"|"expired"; provider:string; provider_customer_id:string|null; provider_subscription_id:string|null; trial_started_at:string|null; trial_ends_at:string|null; current_period_start:string|null; current_period_end:string|null; cancel_at_period_end:boolean; canceled_at:string|null; }
export interface EntitlementSnapshot { plan:BillingPlan; plan_id:string; features:Record<string,boolean>; limits:Record<string,{limit:number;reset_period:string}>; subscription:BillingSubscription|null; }
export interface UsageMetric { used:number; limit:number; remaining:number|null; reset_period:string; }
export interface UsageSummary { period_start:string; plan_id:string; metrics:Record<string,UsageMetric>; }
export interface BillingEvent { id:string; provider:string; event_type:string; processed_at:string|null; created_at:string; payload:Record<string,unknown>; }
async function billingRequest<T>(path:string,init:RequestInit={}):Promise<T>{const r=await fetch(window.location.origin+"/api"+path,{...init,credentials:"include",headers:{"Content-Type":"application/json",...(init.headers??{})}});if(!r.ok){let d="Billing request failed.";try{const b=await r.json();if(typeof b.detail==="string")d=b.detail}catch{}throw new Error(d)}return r.status===204?undefined as T:await r.json() as T}
export const getBillingPlans=()=>billingRequest<{plans:BillingPlan[]}>("/billing/plans");
export const getEntitlements=()=>billingRequest<EntitlementSnapshot>("/billing/entitlements");
export const getSubscription=()=>billingRequest<{plan:BillingPlan;subscription:BillingSubscription|null;plan_id:string}>("/billing/subscription");
export const getUsage=()=>billingRequest<UsageSummary>("/billing/usage");
export const getBillingHistory=()=>billingRequest<{events:BillingEvent[]}>("/billing/history");
export const startProTrial=(days=14)=>billingRequest<{subscription:BillingSubscription}>("/billing/trial",{method:"POST",body:JSON.stringify({days})});
