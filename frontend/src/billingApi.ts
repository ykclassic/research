export interface BillingPlan { id:string; name:string; description:string; monthly_price_minor:number; currency:string; display_order:number; active:boolean; }
export interface BillingSubscription { id:string; user_id:string; plan_id:string; status:"trialing"|"active"|"past_due"|"unpaid"|"paused"|"canceled"|"expired"; provider:string; provider_customer_id:string|null; provider_subscription_id:string|null; trial_started_at:string|null; trial_ends_at:string|null; current_period_start:string|null; current_period_end:string|null; cancel_at_period_end:boolean; canceled_at:string|null; }
export interface EntitlementSnapshot { plan:BillingPlan; plan_id:string; features:Record<string,boolean>; limits:Record<string,{limit:number;reset_period:string}>; subscription:BillingSubscription|null; }
export interface UsageMetric { used:number; limit:number; remaining:number|null; reset_period:string; }
export interface UsageSummary { period_start:string; plan_id:string; metrics:Record<string,UsageMetric>; notifications:Array<{metric:string;threshold_percent:number;used:number;limit_value:number;created_at:string}>; }
export interface BillingEvent { id:string; provider:string; event_type:string; processed_at:string|null; created_at:string; payload:Record<string,unknown>; }

const PROD="https://research-76vr.onrender.com";
const configured=(import.meta.env.VITE_API_BASE_URL??"").trim();
const host=typeof window!=="undefined"?window.location.hostname:"";
const local=host==="localhost"||host==="127.0.0.1"||host==="[::1]";
const API_BASE=(configured&&(!local||!/^https?:\/\/(localhost|127\.0\.0\.1)/i.test(configured)))?configured:(local?(configured||"http://localhost:8000"):PROD);
const csrf=()=>document.cookie.split(";").map(x=>x.trim()).find(x=>x.startsWith("mr_csrf="))?.slice(8)??sessionStorage.getItem("mr_csrf_token");
async function csrfToken(){const r=await fetch(API_BASE+"/api/auth/csrf",{credentials:"include"});if(!r.ok)throw new Error("Authentication session expired.");const token=r.headers.get("X-CSRF-Token");if(!token)throw new Error("CSRF token unavailable.");sessionStorage.setItem("mr_csrf_token",token);return token;}
async function billingRequest<T>(path:string,init:RequestInit={}):Promise<T>{const headers=new Headers(init.headers);headers.set("Content-Type","application/json");if(init.method&&init.method!=="GET"){let token=csrf();if(!token)token=await csrfToken();headers.set("X-CSRF-Token",token)}const r=await fetch(API_BASE+"/api"+path,{...init,credentials:"include",headers});if(!r.ok){let d="Billing request failed.";try{const b=await r.json();if(typeof b.detail==="string")d=b.detail}catch{}throw new Error(d)}return r.status===204?undefined as T:await r.json() as T}
export const getBillingPlans=()=>billingRequest<{plans:BillingPlan[]}>("/billing/plans");
export const getEntitlements=()=>billingRequest<EntitlementSnapshot>("/billing/entitlements");
export const getSubscription=()=>billingRequest<{plan:BillingPlan;subscription:BillingSubscription|null;plan_id:string}>("/billing/subscription");
export const getUsage=()=>billingRequest<UsageSummary>("/billing/usage");
export const getBillingHistory=()=>billingRequest<{events:BillingEvent[]}>("/billing/history");
export const startProTrial=(days=14)=>billingRequest<{subscription:BillingSubscription}>("/billing/trial",{method:"POST",body:JSON.stringify({days})});

export const startCheckout=(plan_id:string)=>billingRequest<{checkout_url:string;checkout_session_id:string;provider:string;plan_id:string}>("/billing/checkout",{method:"POST",body:JSON.stringify({plan_id})});
export const changePlan=(plan_id:string)=>billingRequest<{status:string;plan_id?:string;checkout_url?:string;checkout_session_id?:string}>("/billing/change",{method:"POST",body:JSON.stringify({plan_id})});
export const cancelSubscription=(at_period_end=true)=>billingRequest<Record<string,unknown>>("/billing/cancel",{method:"POST",body:JSON.stringify({at_period_end})});
export const resumeSubscription=()=>billingRequest<Record<string,unknown>>("/billing/resume",{method:"POST"});
