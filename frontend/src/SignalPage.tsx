import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Minus, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, CryptoSignal, getCryptoSignals, User } from "./api";
import type { AppPage } from "./App";
import "./signal.css";

const SIGNAL_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"];

type SignalTone = "strong-buy" | "buy" | "neutral" | "sell" | "strong-sell";

function signalLabel(signal: CryptoSignal["signal"]): string {
  return signal.replace("STRONG_", "Strong ").replace("_", " ").replace("BUY", "Buy").replace("SELL", "Sell");
}

function tone(signal: CryptoSignal["signal"]): SignalTone {
  if (signal === "STRONG_BUY") return "strong-buy";
  if (signal === "BUY") return "buy";
  if (signal === "SELL") return "sell";
  if (signal === "STRONG_SELL") return "strong-sell";
  return "neutral";
}

function SignalIcon({ signal }: { signal: CryptoSignal["signal"] }) {
  if (signal === "BUY" || signal === "STRONG_BUY") return <ArrowUp size={19} strokeWidth={2.5} />;
  if (signal === "SELL" || signal === "STRONG_SELL") return <ArrowDown size={19} strokeWidth={2.5} />;
  return <Minus size={19} strokeWidth={2.5} />;
}

function formatPrice(value: number): string {
  if (value >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (value >= 1) return value.toLocaleString(undefined, { maximumFractionDigits: 5 });
  return value.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

export default function SignalPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: AppPage) => void }) {
  const [signals, setSignals] = useState<CryptoSignal[]>([]);
  const [selected, setSelected] = useState<string>(SIGNAL_SYMBOLS[0]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (force = false) => {
    try {
      setError(null);
      if (force) setRefreshing(true);
      const result = await getCryptoSignals(250);
      setSignals(result.signals);
      setSelected(current => result.signals.some(item => item.symbol === current) ? current : result.signals[0]?.symbol ?? SIGNAL_SYMBOLS[0]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to retrieve crypto signals.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [onLogout]);

  useEffect(() => { void load(); }, [load]);

  const selectedSignal = signals.find(item => item.symbol === selected) ?? null;
  const directional = signals.filter(item => item.signal !== "NEUTRAL").length;

  return <div className="app"><header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button" onClick={() => setPage("market")}>Market Data</button><button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button><button className="nav-button" onClick={() => setPage("analysis")}>Technical Analysis</button><button className="nav-button" onClick={() => setPage("market-structure")}>Market Structure</button><button className="nav-button" onClick={() => setPage("mtf")}>MTF Analysis</button><button className="nav-button active" onClick={() => setPage("signals")}>Signals</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="refresh" onClick={() => void load(true)} disabled={refreshing}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh signals"}</button></div></header><main><section className="hero signal-hero"><div><div className="eyebrow">Phase 7 · Crypto signals</div><h2>Indicator + SMC confluence.</h2><p>Signals are deterministic research outputs built from the existing technical-indicator engine, SMC/market-structure engine, and Daily → H4 → H1 → M15 hierarchy. Crypto pairs only.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>{signals.length ? `${directional}/${signals.length}` : "—"}</strong><span>directional signals</span></div></section>{error && <div className="error"><AlertTriangle size={17}/>{error}</div>}<section className="signal-workspace"><div className="panel signal-panel"><div className="panel-head"><div><h3>Crypto signal scanner</h3><span>Current completed-candle confluence</span></div><ShieldCheck size={20}/></div>{loading ? <div className="empty">Loading crypto signals…</div> : !signals.length ? <div className="empty">No crypto signals are currently available.</div> : <div className="signal-list">{signals.map(item => <button key={item.symbol} className={`signal-row ${selected === item.symbol ? "selected" : ""}`} onClick={() => setSelected(item.symbol)}><div className="signal-symbol"><strong>{item.symbol}</strong><span>Crypto</span></div><div className={`signal-badge ${tone(item.signal)}`}><SignalIcon signal={item.signal}/><strong>{signalLabel(item.signal)}</strong></div><div className="signal-score"><span>Confluence</span><strong>{Math.round(item.confluence * 100)}%</strong></div><div className="signal-price"><span>{formatPrice(item.price)}</span><small>{new Date(item.latest_candle_timestamp).toLocaleTimeString()}</small></div></button>)}</div>}</div><aside className="panel signal-detail"><div className="panel-head"><div><h3>{selectedSignal?.symbol ?? "Signal detail"}</h3><span>Indicator + SMC evidence</span></div></div>{selectedSignal ? <><div className={`signal-detail-status ${tone(selectedSignal.signal)}`}><SignalIcon signal={selectedSignal.signal}/><strong>{signalLabel(selectedSignal.signal)}</strong></div><div className="signal-detail-score"><span>Confluence score</span><strong>{Math.round(selectedSignal.confluence * 100)}%</strong><small>Directional score: {selectedSignal.score.toFixed(3)}</small></div><div className="signal-metrics"><div><span>Price</span><strong>{formatPrice(selectedSignal.price)}</strong></div><div><span>Source</span><strong>{selectedSignal.source}</strong></div><div><span>Updated</span><strong>{new Date(selectedSignal.calculated_at).toLocaleTimeString()}</strong></div><div><span>Latest candle</span><strong>{new Date(selectedSignal.latest_candle_timestamp).toLocaleTimeString()}</strong></div></div><div className="signal-components">{selectedSignal.components.map(component => <div className="signal-component" key={component.timeframe}><div><strong>{component.timeframe}</strong><span>Indicator {component.indicator_score.toFixed(2)} · SMC {component.smc_score.toFixed(2)}</span></div><strong>{component.combined_score.toFixed(2)}</strong></div>)}</div><ul className="signal-evidence">{selectedSignal.evidence.map(item => <li key={item}>{item}</li>)}</ul></> : <div className="empty">Select a crypto pair.</div>}</aside></section><footer>Signals are research outputs, not financial advice or automatic trade instructions. Only completed, current-eligible crypto candle data is used; no signal is generated for forex, stocks, or ETFs.</footer></main></div>;
}
