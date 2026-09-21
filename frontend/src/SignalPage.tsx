import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Check,
  Minus,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { ApiError, CryptoSignal, User, getSignal, logSignal, logout } from "./api";
import { getMarketUniverse, MarketUniverse } from "./settingsApi";
import type { AppPage } from "./App";
import "./signal.css";

type SignalTone = "strong-buy" | "buy" | "neutral" | "sell" | "strong-sell";
type PairStatus = "idle" | "loading" | "ready" | "error";
type PairState = { status: PairStatus; signal?: CryptoSignal; error?: string };

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
  if (signal === "BUY" || signal === "STRONG_BUY") return <ArrowUp size={18} strokeWidth={2.5} />;
  if (signal === "SELL" || signal === "STRONG_SELL") return <ArrowDown size={18} strokeWidth={2.5} />;
  return <Minus size={18} strokeWidth={2.5} />;
}
function formatPrice(value: number | null): string {
  if (value === null) return "—";
  if (value >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (value >= 1) return value.toLocaleString(undefined, { maximumFractionDigits: 5 });
  return value.toLocaleString(undefined, { maximumFractionDigits: 8 });
}
function formatPercent(value: number): string { return Math.round(value * 100) + "%"; }
function formatRiskReward(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(2) + ":1";
}
function formatTime(value: string): string { return new Date(value).toLocaleTimeString(); }
function assetClass(universe: MarketUniverse | null, symbol: string): string {
  if (!universe) return "Market";
  if (universe.symbols.crypto.includes(symbol)) return "Crypto";
  if (universe.symbols.forex.includes(symbol)) return "Forex";
  if (universe.symbols.stocks.includes(symbol)) return "Stocks";
  return "Market";
}
function classCount(universe: MarketUniverse | null, kind: "crypto" | "forex" | "stocks"): number {
  if (!universe) return 0;
  return universe.symbols[kind].filter(symbol => universe.enabled_symbols.includes(symbol)).length;
}
function statusLabel(signal: CryptoSignal): "Qualified" | "Rejected" {
  return signal.qualification_status === "QUALIFIED" ? "Qualified" : "Rejected";
}

export default function SignalPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: AppPage) => void }) {
  const [universe, setUniverse] = useState<MarketUniverse | null>(null);
  const [selected, setSelected] = useState("");
  const [pairStates, setPairStates] = useState<Record<string, PairState>>({});
  const [loadingList, setLoadingList] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loggingSignal, setLoggingSignal] = useState(false);
  const [loggedSignalId, setLoggedSignalId] = useState<string | null>(null);
  const requestId = useRef(0);
  const inFlight = useRef(new Set<string>());

  const loadUniverse = useCallback(async () => {
    try {
      setError(null);
      const result = await getMarketUniverse();
      setUniverse(result);
      setSelected(current => result.enabled_symbols.includes(current) ? current : result.enabled_symbols[0] ?? "");
      setPairStates(current => {
        const next: Record<string, PairState> = {};
        for (const symbol of result.enabled_symbols) next[symbol] = current[symbol] ?? { status: "idle" };
        return next;
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to load enabled trading pairs.");
    } finally {
      setLoadingList(false);
    }
  }, [onLogout]);

  const loadSignal = useCallback(async (symbol: string, force = false) => {
    if (!symbol || inFlight.current.has(symbol)) return;
    const id = ++requestId.current;
    inFlight.current.add(symbol);
    setPairStates(current => ({ ...current, [symbol]: { status: "loading", signal: force ? undefined : current[symbol]?.signal } }));
    try {
      if (force) setRefreshing(true);
      const result = await getSignal(symbol, 250);
      setLoggedSignalId(null);
      if (id === requestId.current || selected === symbol) {
        setPairStates(current => ({ ...current, [symbol]: { status: "ready", signal: result } }));
      }
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to retrieve this trading-pair signal.";
      if (id === requestId.current || selected === symbol) {
        setPairStates(current => ({ ...current, [symbol]: { status: "error", error: message } }));
        if (selected === symbol) setError(message);
      }
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
    } finally {
      inFlight.current.delete(symbol);
      if (selected === symbol) setRefreshing(false);
    }
  }, [onLogout, selected]);

  useEffect(() => { void loadUniverse(); }, [loadUniverse]);
  useEffect(() => { if (selected) void loadSignal(selected); }, [selected, loadSignal]);

  const selectedState = selected ? pairStates[selected] : undefined;
  const selectedSignal = selectedState?.signal;
  const directionalCount = selectedSignal && selectedSignal.signal !== "NEUTRAL" ? 1 : 0;
  const selectedClass = useMemo(() => assetClass(universe, selected), [universe, selected]);
  const selectedStatus = selectedSignal ? statusLabel(selectedSignal) : null;
  const minimumConfidence = selectedSignal?.minimum_confidence ?? 0.82;
  const minimumRiskReward = selectedSignal?.minimum_risk_reward ?? 1.5;
  const confidenceGateFailed = selectedSignal?.qualification_reasons.some(reason => reason.startsWith("Confidence ")) ?? false;
  const riskRewardGateFailed = selectedSignal?.qualification_reasons.some(reason => reason.startsWith("Risk/reward")) ?? false;
  const riskRewardUnavailable = selectedSignal?.risk_reward_status === "UNAVAILABLE";

  return <div className="app">
    <header className="topbar">
      <div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div>
      <nav className="main-nav" aria-label="Research sections">
        <button className="nav-button" onClick={() => setPage("market")}>Market Data</button>
        <button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button>
        <button className="nav-button" onClick={() => setPage("analysis")}>Technical Analysis</button>
        <button className="nav-button" onClick={() => setPage("market-structure")}>Market Structure</button>
        <button className="nav-button" onClick={() => setPage("mtf")}>MTF Analysis</button>
        <button className="nav-button active" onClick={() => setPage("signals")}>Signals</button>
        <button className="nav-button" onClick={() => setPage("signal-outcome")}>Signal Outcome</button>
      </nav>
      <div className="topbar-actions"><span className="user-email">{user.email}</span><button className="refresh" onClick={() => void loadSignal(selected, true)} disabled={refreshing || !selected}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh signal"}</button><button className="logout" onClick={() => void (async () => { try { await logout(); } finally { onLogout(); } })()}>Sign out</button></div>
    </header>
    <main>
      <section className="hero signal-hero">
        <div>
          <div className="eyebrow">Intelligence · Signals</div>
          <h2>Indicator + SMC confluence.</h2>
          <p>Signals are deterministic research outputs from completed candles, technical indicators, market structure and the Daily → H4 → H1 → M15 hierarchy. Select one enabled trading pair below; only the selected pair is requested and calculated.</p>
        </div>
        <div className="hero-stat"><ShieldCheck size={20}/><strong>{directionalCount}/1</strong><span>directional / selected</span></div>
      </section>

      {error && <div className="error"><AlertTriangle size={17}/><span>{error}</span></div>}

      <section className="signal-coverage">
        <div><span>Enabled pairs</span><strong>{universe?.enabled_symbols.length ?? 0}</strong></div>
        <div><span>Crypto</span><strong>{classCount(universe, "crypto")}</strong></div>
        <div><span>Forex</span><strong>{classCount(universe, "forex")}</strong></div>
        <div><span>Stocks</span><strong>{classCount(universe, "stocks")}</strong></div>
      </section>

      <section className="signal-workspace">
        <div className="panel signal-panel">
          <div className="panel-head"><div><h3>Enabled trading pairs</h3><span>Select a pair to generate its signal</span></div><ShieldCheck size={20}/></div>
          {loadingList ? <div className="empty">Loading enabled trading pairs…</div> :
          !universe?.enabled_symbols.length ? <div className="empty">No asset classes are enabled in Settings → Market Data.</div> :
          <div className="signal-list">
            {universe.enabled_symbols.map(symbol => {
              const state = pairStates[symbol] ?? { status: "idle" as PairStatus };
              const item = state.signal;
              const itemStatus = item ? statusLabel(item) : null;
              return <button key={symbol} className={"signal-row " + (selected === symbol ? "selected" : "")} onClick={() => { setSelected(symbol); setError(null); }} aria-label={"Select signal for " + symbol} aria-pressed={selected === symbol}>
                <div className="signal-symbol"><strong>{symbol}</strong><span>{assetClass(universe, symbol)}</span></div>
                <div className={"signal-badge " + (item ? tone(item.signal) : "neutral") + (item ? " " + itemStatus?.toLowerCase() : "")}>
                  {item ? <SignalIcon signal={item.signal}/> : <ShieldCheck size={17}/>}
                  <strong>{item ? itemStatus : state.status === "loading" ? "Calculating…" : state.status === "error" ? "Unavailable" : "Select to calculate"}</strong>
                </div>
                <div className="signal-score"><span>Confidence</span><strong>{item ? formatPercent(item.confidence) : "—"}</strong></div>
                <div className="signal-price"><span>{item ? formatPrice(item.price) : "—"}</span><small>{item ? formatTime(item.latest_candle_timestamp) : ""}</small></div>
              </button>;
            })}
          </div>}
        </div>

        <aside className="panel signal-detail">
          <div className="panel-head"><div><h3>{selected || "Signal detail"}</h3><span>{selectedClass} · completed-candle research</span></div></div>
          {!selected ? <div className="empty">Enable an asset class and select a pair.</div> :
          selectedState?.status === "loading" && !selectedSignal ? <div className="empty">Calculating {selected} from Daily, H4, H1 and M15 completed candles…</div> :
          selectedState?.status === "error" && !selectedSignal ? <div className="empty signal-detail-error"><AlertTriangle size={18}/><span>{selectedState.error}</span><button className="refresh" onClick={() => void loadSignal(selected, true)}>Retry {selected}</button></div> :
          selectedSignal ? <div className="signal-detail-body">
            <div className="signal-pipeline">
              <div className="pipeline-step complete"><Check size={15}/><span>Calculated</span></div>
              <div className="pipeline-line"/>
              <div className={"pipeline-step " + (selectedStatus === "Qualified" ? "qualified" : "inactive")}>{selectedStatus === "Qualified" ? <Check size={15}/> : <X size={15}/>}<span>Qualified</span></div>
              <div className="pipeline-line"/>
              <div className={"pipeline-step " + (selectedStatus === "Rejected" ? "rejected" : "inactive")}>{selectedStatus === "Rejected" ? <X size={15}/> : <Check size={15}/>}<span>Rejected</span></div>
            </div>

            <div className={"signal-detail-status " + tone(selectedSignal.signal) + " " + (selectedStatus === "Qualified" ? "qualified" : "rejected")}>
              <SignalIcon signal={selectedSignal.signal}/>
              <div>
                <strong>{selectedStatus === "Qualified" ? "Calculated — Qualified" : "Calculated — Not qualified"}</strong>
                <span>{signalLabel(selectedSignal.signal)}</span>
              </div>
            </div>

            <div className={"qualification-summary " + (selectedStatus === "Qualified" ? "passed" : "failed")}>
              <div className="qualification-summary-head">
                <strong>{selectedStatus === "Qualified" ? "All qualification gates passed" : "Qualification gate result"}</strong>
                <span>{selectedStatus === "Qualified" ? "This signal meets the configured requirements." : "The signal can have high confidence and still fail another required gate."}</span>
              </div>
              {selectedStatus === "Rejected" && selectedSignal.qualification_reasons.length > 0 && (
                <ul className="qualification-reasons">
                  {selectedSignal.qualification_reasons.map(reason => <li key={reason}>{reason}</li>)}
                </ul>
              )}
            </div>

            <div className="signal-audit-action">
              {selectedSignal.qualification_status === "QUALIFIED" ? (
                <button
                  className="log-signal-button"
                  disabled={loggingSignal || loggedSignalId === selectedSignal.signal_id}
                  onClick={() => void (async () => {
                    setLoggingSignal(true);
                    setError(null);
                    try {
                      await logSignal(selectedSignal);
                      setLoggedSignalId(selectedSignal.signal_id);
                    } catch (err) {
                      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
                      setError(err instanceof Error ? err.message : "Unable to log this signal for outcome audit.");
                    } finally {
                      setLoggingSignal(false);
                    }
                  })()}
                >
                  {loggingSignal ? "Logging signal…" : loggedSignalId === selectedSignal.signal_id ? "Signal Logged" : "Log Signal"}
                </button>
              ) : (
                <span className="signal-audit-note">Outcome audit is available only for qualified signals.</span>
              )}
              <button className="refresh" onClick={() => setPage("signal-outcome")}>Signal Outcome</button>
            </div>

            <div className="signal-detail-score"><span>Confluence</span><strong>{formatPercent(selectedSignal.confluence)}</strong><small>Directional score: {selectedSignal.score.toFixed(3)}</small></div>

            <div className="signal-thresholds">
              <div className={confidenceGateFailed ? "gate-failed" : "gate-passed"}>
                <span>Confidence gate</span>
                <strong>{formatPercent(selectedSignal.confidence)} / {formatPercent(minimumConfidence)} required</strong>
                <small>{confidenceGateFailed ? "FAILED" : "PASSED"}</small>
              </div>
              <div className={riskRewardGateFailed ? "gate-failed" : "gate-passed"}>
                <span>Risk / reward gate</span>
                <strong>{riskRewardUnavailable ? "N/A" : formatRiskReward(selectedSignal.risk_reward)} / {minimumRiskReward.toFixed(2)}:1 required</strong>
                <small>{riskRewardUnavailable ? "UNAVAILABLE — TARGET REQUIRED" : riskRewardGateFailed ? "FAILED" : "PASSED"}</small>
              </div>
            </div>

            <div className="signal-levels">
              <div><span>Entry</span><strong>{formatPrice(selectedSignal.entry_price)}</strong></div>
              <div><span>ATR14</span><strong>{formatPrice(selectedSignal.atr)}</strong></div>
              <div><span>Stop</span><strong>{formatPrice(selectedSignal.stop_loss)}</strong></div>
              <div><span>Target</span><strong>{formatPrice(selectedSignal.take_profit)}</strong></div>
              <div><span>Nearest structural level</span><strong>{formatPrice(selectedSignal.structural_target)}</strong></div>
              <div><span>ATR minimum target</span><strong>{formatPrice(selectedSignal.atr_minimum_target)}</strong></div>
              <div><span>Validated RR</span><strong>{formatRiskReward(selectedSignal.risk_reward)}</strong></div>
            </div>

            <div className="signal-metrics">
              <div><span>Price</span><strong>{formatPrice(selectedSignal.price)}</strong></div>
              <div><span>Source</span><strong>{selectedSignal.source}</strong></div>
              <div><span>Calculated</span><strong>{formatTime(selectedSignal.calculated_at)}</strong></div>
              <div><span>Latest candle</span><strong>{formatTime(selectedSignal.latest_candle_timestamp)}</strong></div>
            </div>

            <div className="signal-section"><h4>Timeframe confluence</h4><div className="signal-components">
              {selectedSignal.components.map(component => <div className="signal-component" key={component.timeframe}>
                <div><strong>{component.timeframe}</strong><span>Indicator {component.indicator_score.toFixed(2)} · SMC {component.smc_score.toFixed(2)}</span></div>
                <strong>{component.combined_score.toFixed(2)}</strong>
              </div>)}
            </div></div>

            <div className="signal-section"><h4>Evidence</h4><ul className="signal-evidence">{selectedSignal.evidence.map(item => <li key={item}>{item}</li>)}</ul></div>

            {selectedStatus === "Qualified" && selectedSignal.qualification_reasons.length > 0 && <div className="signal-section signal-warnings"><h4>Qualification notes</h4><ul className="signal-evidence">{selectedSignal.qualification_reasons.map(item => <li key={item}>{item}</li>)}</ul></div>}
          </div> :
          <div className="empty">Select {selected} to calculate its signal.</div>}
        </aside>
      </section>
      <footer>Signals are research outputs, not financial advice or automatic trade instructions. Only pairs from enabled asset classes are shown; the server validates the selected pair before calculation. No unselected pair is requested by the production signal UI.</footer>
    </main>
  </div>;
}
