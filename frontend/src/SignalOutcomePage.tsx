import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, Clock3, RefreshCw, ShieldCheck, X } from "lucide-react";
import { ApiError, getSignalOutcome, getSignalOutcomes, logout, SignalOutcomeRecord, User } from "./api";
import type { AppPage } from "./App";
import "./signal-outcome.css";

function price(value: number | null): string {
  if (value == null) return "—";
  if (value >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (value >= 1) return value.toLocaleString(undefined, { maximumFractionDigits: 5 });
  return value.toLocaleString(undefined, { maximumFractionDigits: 8 });
}
function time(value: string | null): string { return value ? new Date(value).toLocaleString() : "—"; }
function latency(value: number | null): string {
  if (value == null) return "—";
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) return seconds + "s";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + "m";
  return Math.floor(minutes / 60) + "h " + (minutes % 60) + "m";
}
function statusLabel(status: SignalOutcomeRecord["outcome"]): string {
  if (status === "TARGET_HIT") return "Take profit hit";
  if (status === "STOP_LOSS_HIT") return "Stop loss hit";
  if (status === "AMBIGUOUS") return "Ambiguous — same candle";
  return "Pending";
}
function statusIcon(status: SignalOutcomeRecord["outcome"]) {
  if (status === "TARGET_HIT") return <Check size={16}/>;
  if (status === "STOP_LOSS_HIT") return <X size={16}/>;
  if (status === "AMBIGUOUS") return <AlertTriangle size={16}/>;
  return <Clock3 size={16}/>;
}

export default function SignalOutcomePage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: AppPage) => void }) {
  const [records, setRecords] = useState<SignalOutcomeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getSignalOutcomes(100);
      setRecords(next);
      for (const record of next.slice(0, 20)) {
        if (record.outcome !== "PENDING") continue;
        try {
          const refreshed = await getSignalOutcome(record.signal_id, true);
          setRecords(current => current.map(item => item.signal_id === refreshed.signal_id ? refreshed : item));
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
        }
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to load signal outcomes.");
    } finally {
      setLoading(false);
    }
  }, [onLogout]);

  useEffect(() => { void load(); }, [load]);

  const refresh = async (signalId: string) => {
    setRefreshing(signalId);
    setError(null);
    try {
      const updated = await getSignalOutcome(signalId, true);
      setRecords(current => current.map(item => item.signal_id === updated.signal_id ? updated : item));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to refresh signal outcome.");
    } finally {
      setRefreshing(null);
    }
  };

  return <div className="app">
    <header className="topbar">
      <div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div>
      <nav className="main-nav" aria-label="Signal sections">
        <button className="nav-button" onClick={() => setPage("signals")}><ArrowLeft size={15}/> Signals</button>
        <button className="nav-button active" onClick={() => setPage("signal-outcome")}>Signal Outcome</button>
      </nav>
      <div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={() => void (async () => { try { await logout(); } finally { onLogout(); } })()}>Sign out</button></div>
    </header>
    <main>
      <section className="hero signal-outcome-hero">
        <div><div className="eyebrow">Signals · Outcome audit</div><h2>First official target touch.</h2><p>Only signals explicitly logged from the Signals page enter this audit. The outcome is determined from the first post-dispatch target/stop touch, not from a later trade exit.</p></div>
        <div className="hero-stat"><ShieldCheck size={20}/><strong>{records.length}</strong><span>logged signals</span></div>
      </section>
      {error && <div className="error"><AlertTriangle size={17}/>{error}</div>}
      {loading ? <div className="empty">Loading logged signal outcomes…</div> :
      records.length === 0 ? <section className="panel signal-outcome-empty"><ShieldCheck size={22}/><strong>No signals have been logged.</strong><span>Return to Signals and click “Log Signal” on a qualified signal to begin the audit.</span><button className="refresh" onClick={() => setPage("signals")}>Back to Signals</button></section> :
      <section className="signal-outcome-list">
        {records.map(record => <article className="panel signal-outcome-card" key={record.signal_id}>
          <div className="signal-outcome-head">
            <div><strong>{record.symbol}</strong><span>{record.signal} · {record.timeframe} · {record.provider}</span></div>
            <div className={"outcome-status " + record.outcome.toLowerCase()}>{statusIcon(record.outcome)}<strong>{statusLabel(record.outcome)}</strong></div>
          </div>
          <div className="signal-outcome-grid">
            <div><span>Score</span><strong>{record.score.toFixed(3)}</strong></div>
            <div><span>Confidence</span><strong>{Math.round(record.confidence * 100)}%</strong></div>
            <div><span>Entry</span><strong>{price(record.entry_price)}</strong></div>
            <div><span>Target</span><strong>{price(record.target_price)}</strong></div>
            <div><span>Stop</span><strong>{price(record.stop_loss)}</strong></div>
            <div><span>Dispatched</span><strong>{time(record.dispatched_at)}</strong></div>
            <div><span>Target tagged</span><strong>{time(record.target_tagged_at)}</strong></div>
            <div><span>Stop tagged</span><strong>{time(record.stop_tagged_at)}</strong></div>
            <div><span>Target latency</span><strong>{latency(record.target_tag_latency_seconds)}</strong></div>
            <div><span>Stop latency</span><strong>{latency(record.stop_tag_latency_seconds)}</strong></div>
            <div><span>First touch</span><strong>{time(record.first_touch_timestamp)}</strong></div>
            <div><span>First touch price</span><strong>{price(record.first_touch_price)}</strong></div>
          </div>
          <div className="signal-outcome-foot">
            <span>Engine {record.signal_engine_version} · revision {record.revision} · observed {time(record.observed_at)}</span>
            {record.coverage_warning && <span className="coverage-warning">{record.coverage_warning}</span>}
            <button className="refresh" onClick={() => void refresh(record.signal_id)} disabled={refreshing === record.signal_id}><RefreshCw size={14}/>{refreshing === record.signal_id ? "Checking" : "Refresh status"}</button>
          </div>
        </article>)}
      </section>}
      <footer>Outcome tracking begins only after Log Signal is clicked. A completed 15-minute OHLC candle proves a level was touched within that candle; it does not provide an exact intrabar second.</footer>
    </main>
  </div>;
}
