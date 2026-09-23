const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
function csrf(): string | null { const cookie = document.cookie.split(";").map(item => item.trim()).find(item => item.startsWith("mr_csrf=")); return cookie ? decodeURIComponent(cookie.slice("mr_csrf=".length)) : null; }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers); if (init.body) headers.set("Content-Type","application/json");
  if (init.method && init.method !== "GET") { const token = csrf(); if (token) headers.set("X-CSRF-Token", token); }
  const response = await fetch(API_BASE + path, { ...init, headers, credentials: "include" });
  if (!response.ok) { let message = "Request failed: " + response.status; try { const body = await response.json() as {detail?:string}; if(body.detail) message=body.detail; } catch {} throw new Error(message); }
  if(response.status===204) return undefined as T; return await response.json() as T;
}
async function authenticatedMutation<T>(path:string, init:RequestInit):Promise<T>{return request<T>(path,init);}
export interface ResearchSnapshot { id:string; symbol:string; snapshot_type:string; snapshot_at:string; source_history_id:string|null; state:Record<string,unknown>; engine_version:string; provenance:ResearchProvenance[]; }
export interface ResearchProvenance { id:string; snapshot_id:string; claim_type:string; claim:string; analysis:string; data:Record<string,unknown>; sources:string[]; observed_at:string; method:string; engine_version:string; }
export interface ResearchChange { category:string; field:string; previous:unknown; current:unknown; significance:string; }
export interface ResearchComparison { symbol:string; baseline_type:string; current:ResearchSnapshot; baseline:ResearchSnapshot|null; changes:ResearchChange[]; summary:string; evidence_note:string; }
export interface ResearchWatchpoint { id:string; symbol:string; name:string; condition_type:string; field:string; operator:string; value:unknown; timeframe:string|null; enabled:boolean; last_state:boolean|null; last_triggered_at:string|null; created_at:string; updated_at:string; }
export interface ResearchWatchpointEvent { id:string; watchpoint_id:string; symbol:string; event_type:string; message:string; observed_value:unknown; triggered_at:string; }
export interface ResearchCatalyst { id:string; title:string; event_type:string; source:string; source_url:string|null; event_timestamp:string; affected_assets:string[]; sentiment:string|null; market_reaction:Record<string,unknown>; provider:string; }
export async function saveResearchSnapshot(id:string):Promise<ResearchSnapshot>{return (await authenticatedMutation<{item:ResearchSnapshot}>("/api/research-intelligence/snapshots/"+encodeURIComponent(id)+"/save",{method:"POST"})).item;}
export async function getResearchTimeline(symbol:string):Promise<ResearchSnapshot[]>{return (await request<{items:ResearchSnapshot[]}>("/api/research-intelligence/timeline?symbol="+encodeURIComponent(symbol))).items;}
export async function getResearchComparison(symbol:string,baseline:string):Promise<ResearchComparison>{return request<ResearchComparison>("/api/research-intelligence/compare?symbol="+encodeURIComponent(symbol)+"&baseline="+encodeURIComponent(baseline));}
export async function getResearchWatchpoints(symbol?:string):Promise<ResearchWatchpoint[]>{const q=symbol?"?symbol="+encodeURIComponent(symbol):"";return (await request<{items:ResearchWatchpoint[]}>("/api/research-intelligence/watchpoints"+q)).items;}
export async function createResearchWatchpoint(payload:Pick<ResearchWatchpoint,"symbol"|"name"|"condition_type"|"field"|"operator"|"value">):Promise<ResearchWatchpoint>{return (await authenticatedMutation<{item:ResearchWatchpoint}>("/api/research-intelligence/watchpoints",{method:"POST",body:JSON.stringify({...payload,enabled:true})})).item;}
export async function deleteResearchWatchpoint(id:string):Promise<void>{await authenticatedMutation<void>("/api/research-intelligence/watchpoints/"+encodeURIComponent(id),{method:"DELETE"});}
export async function getResearchWatchpointEvents():Promise<ResearchWatchpointEvent[]>{return (await request<{items:ResearchWatchpointEvent[]}>("/api/research-intelligence/watchpoint-events")).items;}
export async function getResearchCatalysts(symbol:string):Promise<ResearchCatalyst[]>{return (await request<{items:ResearchCatalyst[]}>("/api/research-intelligence/catalysts?symbol="+encodeURIComponent(symbol)+"&days=7&limit=25")).items;}
