import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Check, Clock3, RefreshCw, ShieldCheck, X, AlertTriangle } from "lucide-react";
import { ApiError, SignalOutcomeRecord, getSignalOutcome, getSignalOutcomes, logout, User } from "./api";
import type { AppPage } from "./App";
import "./signal-outcome.css";

function price(value: number | null): string { return value == null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: value >= 1000 ? 2 : 8 }); }
function time(value: string | null): string { return value ? new Date(value).toLocaleString() : "—"; }
function statusLabel(status: SignalOutcomeRecord["outcome"]): string { if (status === "TARGET_HIT") return "Take profit hit"; if (status === "STOP_LOSS_HIT") return "Stop loss hit"; if (status === "AMBIGUOUS") return "Ambiguous"; return "Pending"; }
function statusIcon(status: SignalOutcomeRecord["outcome"]) { if (status === "TARGET_HIT") return <Check size={16}/>; if (status === "STOP_LOSS_HIT") return <X size={16}/>; if (status === "AMBIGUOUS") return <AlertTriangle size={16}/>; return <Clock3 size={16}/>; }

export default function SignalOutcomePage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: AppPage) => void }) {
  const [records, setRecords] = useState<SignalOutcomeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async (refreshPending = true) => {
    setLoading(true); setError(null);
    try {
      let next = await getSignalOutcomes(50);
      if (refreshPending) {
        for (const record of next.slice(0, 20)) {
          if (record.outcome !== "PENDING") continue;
          try { const refreshed = await getSignalOutcome(record.signal_id, true); next = next.map(item => item.signal_id === refreshed.signal_id ? refreshed : item); }
          catch (err) { if (err instanceof ApiError && err.status === 401) { onLogout(); return; } }
        }
      }
      setRecords(next);
    } catch (err) { if (err instanceof ApiError && err.status === 401) { onLogout(); return; } setError(err instanceof Error ? err.message : "Unable to load signal outcomes."); }
    finally { setLoading(false); setRefreshing(false); }
  }, [onLogout]);
  useEffect(() => { void load(true); }, [load]);
  const refresh = async (signalId: string) => {
    setRefreshing(true); setError(null);
    try { const updated = await getSignalOutcome(signalId, true); setRecords(current => current.map(item => item.signal_id === updated.signal_id ? updated : item)); }
    catch (err) { if (err instanceof ApiError && err.status === 401) { onLogout(); return; } setError(err instanceof Error ? err.message : "Unable to refresh signal outcome."); }
    finally { setRefreshing(false); }
  };
  return <div className="app">
    <header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div>
      <nav className="main-nav" aria-label="Signal sections"><button className="nav-button" onClick={() => setPage("signals")}><ArrowLeft size={15}/> Signals</button><button className="nav-button active">Signal Outcome</button></nav>
      <div className="topbar-actions"><span className="user-email">{user.email}</span><button className="refresh" onClick={() => void load(true)} disabled={refreshing}><RefreshCw size={16}/>{refreshing ? "Refreshing" : "Refresh outcomes"}</button><button className="logout" onClick={() => void (async () => { try { await logout(); } finally { onLogout(); } })()}>Sign out</button></div>
    </header>
    <main><section className="hero signal-outcome-hero"><div><div className="eyebrow">Signals · Outcome audit</div><h2>First official target touch.</h2><p>Only signals explicitly logged from the Signals page are tracked. The audit stops at the first post-dispatch target or stop touch; it does not wait for or infer a later trade exit.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>{records.length}</strong><span>logged signals</span></div></section>
      {error && <div className="error"><AlertTriangle size={17}/>{error}</div>}
      {loading ? <div className="empty">Loading logged signal outcomes…</div> : records.length === 0 ? <section className="panel signal-outcome-empty"><ShieldCheck size={22}/><strong>No signals have been logged.</strong><span>Return to Signals and click “Log Signal” on a generated signal to start outcome tracking.</span><button className="refresh" onClick={() => setPage("signals")}>Back to Signals</button></section> :
      <section className="signal-outcome-list">{records.map(record => <article className="panel signal-outcome-card" key={record.signal_id}>
        <div className="signal-outcome-head"><div><strong>{record.symbol}</strong><span>{record.signal} · {record.timeframe} · {record.provider}</span></div><div className={"outcome-status " + record.outcome.toLowerCase()}>{statusIcon(record.outcome)}<strong>{statusLabel(record.outcome)}</strong></div></div>
        <div className="signal-outcome-grid"><div><span>Score</span><strong>{record.score.toFixed(3)}</strong></div><div><span>Confidence</span><strong>{Math.round(record.confidence * 100)}%</strong></div><div><span>Entry</span><strong>{price(record.entry_price)}</strong></div><div><span>Target</span><strong>{price(record.target_price)}</strong></div><div><span>Stop</span><strong>{price(record.stop_loss)}</strong></div><div><span>Dispatched</span><strong>{time(record.dispatched_at)}</strong></div><div><span>First touch</span><strong>{time(record.first_touch_timestamp)}</strong></div><div><span>First touch price</span><strong>{price(record.first_touch_price)}</strong></div></div>
        <div className="signal-outcome-foot"><span>{record.outcome === "TARGET_HIT" ? "Target latency: " + Math.round((record.target_tag_latency_seconds ?? 0) / 60) + " min" : record.outcome === "STOP_LOSS_HIT" ? "Stop latency: " + Math.round((record.stop_tag_latency_seconds ?? 0) / 60) + " min" : record.outcome === "AMBIGUOUS" ? "Same candle touched target and stop; intrabar order is unknown." : "No official target or stop touch detected yet."}</span>{record.coverage_warning && <span className="coverage-warning">{record.coverage_warning}</span>}<button className="refresh" onClick={() => void refresh(record.signal_id)} disabled={refreshing}><RefreshCw size={14}/>Refresh status</button></div>
      </article>)}</section>}
      <footer>Outcome tracking begins only after Log Signal is clicked. A completed OHLC candle proves that a level was touched within that candle, not the exact intrabar second.</footer>
    </main></div>;
}