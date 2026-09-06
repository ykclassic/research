export type HistoryRecordType = "REPORT" | "SEARCH" | "AI_ANALYSIS";
export interface HistoryItem { id: string; user_id: string; record_type: HistoryRecordType; symbol: string | null; query: string | null; title: string | null; payload: Record<string, unknown>; saved: boolean; created_at: string; updated_at: string; }
export interface HistoryNote { id: string; history_id: string; note: string; created_at: string; updated_at: string; }
export interface HistoryDetail { item: HistoryItem; notes: HistoryNote[]; }
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
function csrf(): string | null { const cookie = document.cookie.split(";").map(item => item.trim()).find(item => item.startsWith("mr_csrf=")); return cookie ? decodeURIComponent(cookie.slice("mr_csrf=".length)) : null; }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers); headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") { const token = csrf(); if (token) headers.set("X-CSRF-Token", token); }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) { let message = `Request failed: ${response.status}`; try { const body = await response.json() as { detail?: string }; if (body.detail) message = body.detail; } catch {} throw new Error(message); }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}
export async function getResearchHistory(filters: { type?: HistoryRecordType; symbol?: string; saved?: boolean; limit?: number } = {}): Promise<HistoryItem[]> {
  const params = new URLSearchParams(); if (filters.type) params.set("record_type", filters.type); if (filters.symbol) params.set("symbol", filters.symbol); if (filters.saved !== undefined) params.set("saved", String(filters.saved)); params.set("limit", String(filters.limit ?? 100));
  return (await request<{ items: HistoryItem[] }>(`/api/research-history?${params}`)).items;
}
export async function getResearchHistoryDetail(id: string): Promise<HistoryDetail> { return request<HistoryDetail>(`/api/research-history/${encodeURIComponent(id)}`); }
export async function saveResearchHistory(id: string): Promise<HistoryItem> { return (await request<{ item: HistoryItem }>(`/api/research-history/${encodeURIComponent(id)}/save`, { method: "POST" })).item; }
export async function unsaveResearchHistory(id: string): Promise<void> { await request<void>(`/api/research-history/${encodeURIComponent(id)}/save`, { method: "DELETE" }); }
export async function addResearchNote(id: string, note: string): Promise<HistoryNote> { return (await request<{ note: HistoryNote }>(`/api/research-history/${encodeURIComponent(id)}/notes`, { method: "POST", body: JSON.stringify({ note }) })).note; }
export async function deleteResearchHistory(id: string): Promise<void> { await request<void>(`/api/research-history/${encodeURIComponent(id)}`, { method: "DELETE" }); }
