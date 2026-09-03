import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, getMultiTimeframeAnalysis, User, MultiTimeframeResult } from "./api";
import type { AppPage } from "./App";
import "./market-structure.css";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];

export default function MTFAnalysisPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: AppPage) => void }) {
  const [symbol, setSymbol] = useState("BTC/USD");
  const [result, setResult] = useState<MultiTimeframeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (force = false) => {
    try {
      setError(null);
      if (force) setRefreshing(true);
      setResult(await getMultiTimeframeAnalysis(symbol, 250));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to retrieve multi-timeframe research.");
    } finally { setLoading(false); setRefreshing(false); }
  }, [symbol, onLogout]);

  useEffect(() => { void load(); }, [load]);

  return <div className="app"><header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button" onClick={() => setPage("market")}>Market Data</button><button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button><button className="nav-button" onClick={() => setPage("analysis")}>Technical Analysis</button><button className="nav-button" onClick={() => setPage("market-structure")}>Market Structure</button><button className="nav-button active" onClick={() => setPage("mtf")}>MTF Analysis</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="refresh" onClick={() => void load(true)} disabled={refreshing || loading}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh research"}</button></div></header><main><section className="hero"><div><div className="eyebrow">Phase 7 · Multi-timeframe analysis</div><h2>Daily → H4 → H1 → M15 hierarchy.</h2><p>Higher timeframes establish directional context; lower timeframes refine the setup and entry confirmation. The conclusion is derived server-side from canonical completed-candle data and Phase 6 structure events.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>{result ? `${result.research.alignment_count}/4` : "—"}</strong><span>MTF alignment</span></div></section>{error && <div className="error"><AlertTriangle size={17}/>{error}</div>}<section className="mtf-controls"><label>Asset<select value={symbol} onChange={e => setSymbol(e.target.value)}>{SYMBOLS.map(item => <option key={item}>{item}</option>)}</select></label></section>{loading ? <div className="panel empty">Loading multi-timeframe research…</div> : result ? <><section className="mtf-hierarchy">{result.timeframes.map(item => <article className="panel mtf-card" key={item.timeframe}><div className="panel-head"><div><span className="mtf-timeframe">{item.timeframe}</span><h3>{item.conclusion.replace(/^.*?└──\s*/, "")}</h3></div><strong className={`mtf-bias ${item.bias.toLowerCase()}`}>{item.bias}</strong></div><div className="mtf-confidence"><span>Confidence</span><strong>{Math.round(item.confidence * 100)}%</strong></div><ul>{item.evidence.map(evidence => <li key={evidence}>{evidence}</li>)}</ul><small>Completed candles: {item.candle_count} · Latest: {new Date(item.latest_candle_timestamp).toLocaleString()}</small></article>)}</section><section className="panel mtf-conclusion"><div className="panel-head"><div><div className="eyebrow">Structured research conclusion</div><h3>Current MTF assessment</h3></div><ShieldCheck size={20}/></div><div className="mtf-conclusion-grid"><div><span>MTF Alignment</span><strong>{result.research.alignment_count}/4</strong></div><div><span>Bias</span><strong>{result.research.bias}</strong></div><div><span>Confidence</span><strong>{Math.round(result.research.confidence * 100)}%</strong></div></div><div className="mtf-setup"><span>Primary setup</span><strong>{result.research.primary_setup}</strong></div><div className="mtf-setup"><span>Invalidation</span><strong>{result.research.invalidation}</strong></div><pre>{result.research.conclusion}</pre></section></> : <div className="panel empty">No multi-timeframe result available.</div>}<footer>Phase 7 is research-only. Snapshot lifecycle status from Phase 6 is suitable for current-state research; historical backtests must recompute state causally at each decision timestamp.</footer></main></div>;
}
