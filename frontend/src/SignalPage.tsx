import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Minus, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, CryptoSignal, User, getSignal } from "./api";
import { getMarketUniverse, MarketUniverse } from "./settingsApi";
import type { AppPage } from "./App";
import "./signal.css";

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
function assetClass(universe: MarketUniverse | null, symbol: string): string {
  if (!universe) return "Market";
  if (universe.symbols.crypto.includes(symbol)) return "Crypto";
  if (universe.symbols.forex.includes(symbol)) return "Forex";
  if (universe.symbols.stocks.includes(symbol)) return "Stocks";
  return "Market";
}

export default function SignalPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: AppPage) => void }) {
  const [universe, setUniverse] = useState<MarketUniverse | null>(null);
  const [selected, setSelected] = useState("");
  const [signal, setSignal] = useState<CryptoSignal | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingSignal, setLoadingSignal] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const loadUniverse = useCallback(async () => {
    try {
      setError(null);
      const result = await getMarketUniverse();
      setUniverse(result);
      setSelected(current => result.enabled_symbols.includes(current) ? current : result.enabled_symbols[0] ?? "");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to load enabled trading pairs.");
    } finally {
      setLoadingList(false);
    }
  }, [onLogout]);

  const loadSignal = useCallback(async (symbol: string, force = false) => {
    if (!symbol) { setSignal(null); return; }
    const id = ++requestId.current;
    try {
      setError(null);
      if (force) setRefreshing(true);
      setLoadingSignal(true);
      const result = await getSignal(symbol, 250);
      if (id === requestId.current) setSignal(result);
    } catch (err) {
      if (id !== requestId.current) return;
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setSignal(null);
      setError(err instanceof Error ? err.message : "Unable to retrieve the selected trading-pair signal.");
    } finally {
      if (id === requestId.current) {
        setLoadingSignal(false);
        setRefreshing(false);
      }
    }
  }, [onLogout]);

  useEffect(() => { void loadUniverse(); }, [loadUniverse]);
  useEffect(() => { if (selected) void loadSignal(selected); }, [selected, loadSignal]);

  const directional = signal && signal.signal !== "NEUTRAL" ? 1 : 0;
  const enabledCount = universe?.enabled_symbols.length ?? 0;
  const selectedClass = useMemo(() => assetClass(universe, selected), [universe, selected]);

  return <div className="app"><header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button" onClick={() => setPage("market")}>Market Data</button><button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button><button className="nav-button" onClick={() => setPage("analysis")}>Technical Analysis</button><button className="nav-button" onClick={() => setPage("market-structure")}>Market Structure</button><button className="nav-button" onClick={() => setPage("mtf")}>MTF Analysis</button><button className="nav-button active" onClick={() => setPage("signals")}>Signals</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="refresh" onClick={() => void loadSignal(selected, true)} disabled={refreshing || loadingSignal || !selected}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh signal"}</button></div></header><main><section className="hero signal-hero"><div><div className="eyebrow">Signal research</div><h2>One selected trading pair at a time.</h2><p>Signals are calculated from completed-candle indicator, market-structure and multi-timeframe evidence for the pair you select. The available pair list follows your Market Data settings.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>{directional}</strong><span>{enabledCount} enabled pairs</span></div></section>{error && <div className="error"><AlertTriangle size={17}/>{error}</div>}<section className="signal-workspace"><div className="panel signal-panel"><div className="panel-head"><div><h3>Enabled trading pairs</h3><span>Select a pair to calculate its signal</span></div><ShieldCheck size={20}/></div>{loadingList ? <div className="empty">Loading enabled trading pairs…</div> : !universe?.enabled_symbols.length ? <div className="empty">No asset classes are enabled in Market Data settings.</div> : <div className="signal-list">{universe.enabled_symbols.map(symbol => <button key={symbol} className={`signal-row ${selected === symbol ? "selected" : ""}`} onClick={() => setSelected(symbol)}><div className="signal-symbol"><strong>{symbol}</strong><span>{assetClass(universe, symbol)}</span></div><div className="signal-badge neutral"><ShieldCheck size={17}/><strong>{selected === symbol && signal ? signalLabel(signal.signal) : "Select"}</strong></div><div className="signal-score"><span>{selected === symbol && signal ? "Confluence" : "Signal"}</span><strong>{selected === symbol && signal ? `${Math.round(signal.confluence * 100)}%` : "—"}</strong></div><div className="signal-price"><span>{selected === symbol && signal ? formatPrice(signal.price) : "—"}</span><small>{selected === symbol && signal ? new Date(signal.latest_candle_timestamp).toLocaleTimeString() : ""}</small></div></button>)}</div>}</div><aside className="panel signal-detail"><div className="panel-head"><div><h3>{selected || "Signal detail"}</h3><span>{selectedClass} · completed-candle research</span></div></div>{loadingSignal ? <div className="empty">Calculating {selected} signal…</div> : signal ? <><div className={`signal-detail-status ${tone(signal.signal)}`}><SignalIcon signal={signal.signal}/><strong>{signalLabel(signal.signal)}</strong></div><div className="signal-detail-score"><span>Confluence score</span><strong>{Math.round(signal.confluence * 100)}%</strong><small>Directional score: {signal.score.toFixed(3)} · Risk/reward: {signal.risk_reward.toFixed(2)}</small></div><div className="signal-metrics"><div><span>Price</span><strong>{formatPrice(signal.price)}</strong></div><div><span>Source</span><strong>{signal.source}</strong></div><div><span>Updated</span><strong>{new Date(signal.calculated_at).toLocaleTimeString()}</strong></div><div><span>Latest candle</span><strong>{new Date(signal.latest_candle_timestamp).toLocaleTimeString()}</strong></div></div><div className="signal-components">{signal.components.map(component => <div className="signal-component" key={component.timeframe}><div><strong>{component.timeframe}</strong><span>Indicator {component.indicator_score.toFixed(2)} · SMC {component.smc_score.toFixed(2)}</span></div><strong>{component.combined_score.toFixed(2)}</strong></div>)}</div><ul className="signal-evidence">{signal.evidence.map(item => <li key={item}>{item}</li>)}</ul></> : <div className="empty">{selected ? `Select ${selected} to calculate its signal.` : "Enable at least one asset class in Settings → Market Data."}</div>}</aside></section><footer>Signals are research outputs, not financial advice or automatic trade instructions. Only enabled trading pairs can be selected; the server validates the selected pair against the user's settings before calculating its signal.</footer></main></div>;
}
