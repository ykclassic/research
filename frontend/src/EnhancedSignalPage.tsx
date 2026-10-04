import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Lock, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { ApiError, EnhancedSignalResponse, User, getEnhancedSignal, logout } from "./api";
import { getMarketUniverse, MarketUniverse } from "./settingsApi";
import type { AppPage } from "./App";
import "./enhanced-signal.css";

const FALLBACK_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "SUI/USDT"];
function formatPrice(value: number | null | undefined): string { if (value == null) return "—"; return value >= 1000 ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value.toLocaleString(undefined, { maximumFractionDigits: 6 }); }
function CheckRow({ label, passed, value }: { label: string; passed: boolean; value?: string }) { return <div className={passed ? "enhanced-check passed" : "enhanced-check failed"}>{passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}<span>{label}</span><strong>{value ?? (passed ? "PASS" : "FAIL")}</strong></div>; }
function EvidenceRow({ item }: { item: { label: string; passed: boolean; value: string; detail: string } }) { return <details className={item.passed ? "enhanced-evidence-row passed" : "enhanced-evidence-row failed"}><summary>{item.passed ? <CheckCircle2 size={15}/> : <XCircle size={15}/>}<span>{item.label}</span><strong>{item.value}</strong></summary><p>{item.detail}</p></details>; }

export default function EnhancedSignalPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (p: AppPage) => void }) {
  const [universe, setUniverse] = useState<MarketUniverse | null>(null);
  const [symbol, setSymbol] = useState("");
  const [data, setData] = useState<EnhancedSignalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const loadUniverse = useCallback(async () => { try { const next = await getMarketUniverse(); setUniverse(next); setSymbol(current => current || next.enabled_symbols[0] || FALLBACK_SYMBOLS.find(s => next.enabled_symbols.includes(s)) || ""); } catch (e) { if (e instanceof ApiError && e.status === 401) onLogout(); else setError(e instanceof Error ? e.message : "Unable to load enabled markets."); } }, [onLogout]);
  const calculate = useCallback(async () => { if (!symbol) return; setBusy(true); setError(null); try { setData(await getEnhancedSignal(symbol)); } catch (e) { if (e instanceof ApiError && e.status === 401) { onLogout(); return; } setData(null); setError(e instanceof Error ? e.message : "Enhanced Signal calculation failed."); } finally { setBusy(false); } }, [symbol, onLogout]);
  useEffect(() => { void loadUniverse(); }, [loadUniverse]);
  const signal = data?.signal; const checks = data?.checks; const bullish = signal?.signal === "BUY" || signal?.signal === "STRONG_BUY"; const directional = signal?.signal !== "NEUTRAL";
  return <div className="app">
    <header className="topbar"><div className="product-brand"><img src="/profitforge-logo.svg" alt="ProfitForge"/><div><div className="eyebrow">Premium Intelligence</div><h1>ProfitForge</h1></div></div>
      <nav className="main-nav" aria-label="Signal sections"><button className="nav-button" onClick={() => setPage("signals")}>Signals</button><button className="nav-button active">Enhanced Signal</button><button className="nav-button" onClick={() => setPage("signal-intelligence")}>Signal Intelligence</button><button className="nav-button" onClick={() => setPage("signal-outcome")}>Signal Outcome</button></nav>
      <div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={() => void (async () => { try { await logout(); } finally { onLogout(); } })()}>Sign out</button></div></header>
    <main>
      <section className="hero enhanced-hero"><div><div className="eyebrow">Premium / Professional · Enhanced Signal</div><h2>Selective price-action and SMC execution model.</h2><p>Daily → 4H → 1H bias, 15M setup, 5M confirmation, liquidity sweep, displacement, structural invalidation and opposing-liquidity targets. A failed hard gate produces NO TRADE rather than a weak signal.</p></div><div className="enhanced-hero-badge"><ShieldCheck size={18}/><span>Deterministic · auditable</span></div></section>
      {error && <div className="error"><AlertTriangle size={17}/>{error}</div>}
      <section className="panel enhanced-controls"><div><h3>Calculate Enhanced Signal</h3><span>Only the selected enabled pair is requested.</span></div><div className="enhanced-actions"><select value={symbol} onChange={e => setSymbol(e.target.value)} disabled={busy || !universe}>{universe?.enabled_symbols.map(item => <option key={item}>{item}</option>)}</select><button className="refresh" onClick={() => void calculate()} disabled={busy || !symbol}><RefreshCw size={15}/>{busy ? "Calculating…" : "Calculate"}</button></div></section>
      {!data && !busy && !error && <section className="panel enhanced-empty"><Lock size={22}/><div><strong>Enhanced Signal is selective by design.</strong><p>Calculate a configured market to evaluate the complete hard-gate checklist.</p></div></section>}
      {busy && <section className="panel enhanced-empty"><RefreshCw className="spin" size={22}/><div><strong>Evaluating completed candles…</strong><p>Validating HTF structure, entry conditions, risk and target path.</p></div></section>}
      {data && signal && checks && <section className="enhanced-result">
        <section className={"panel enhanced-signal-card " + checks.decision_status.toLowerCase().replace("_","-")}>
          <div className="enhanced-signal-head">
            <div>
              <div className="eyebrow">Decision</div>
              <div className={"enhanced-decision-status " + checks.decision_status.toLowerCase().replace("_","-")}>
                {checks.decision_status === "QUALIFIED" ? <CheckCircle2 size={22}/> : checks.decision_status === "WAIT" ? <RefreshCw size={22}/> : <XCircle size={22}/>}
                <strong>{checks.decision_status.replace("_"," ")}</strong>
              </div>
              <span>{checks.decision_status === "QUALIFIED" ? "All hard gates and execution quality factors passed." : checks.decision_status === "WAIT" ? "Context is viable, but execution confirmation is still incomplete." : "A hard invalidation condition failed. No trade is permitted."}</span>
            </div>
            <div className="enhanced-quality"><strong>{Math.round(checks.quality_score * 100)}/100</strong><span>setup quality</span></div>
          </div>
          <div className="enhanced-levels"><div><span>Entry</span><strong>{formatPrice(signal.entry_price)}</strong></div><div><span>Stop</span><strong>{formatPrice(signal.stop_loss)}</strong></div><div><span>Target</span><strong>{formatPrice(signal.take_profit)}</strong></div><div><span>RR</span><strong>{signal.risk_reward == null ? "—" : signal.risk_reward.toFixed(2) + ":1"}</strong></div></div>
          <div className="enhanced-next-confirmation"><strong>Next confirmation required</strong><span>{checks.next_confirmation}</span></div>
          <div className="enhanced-calibration">
            {checks.calibrated_probability_available && checks.calibrated_probability != null
              ? <><div><span>Calibrated TP probability</span><strong>{(checks.calibrated_probability * 100).toFixed(1)}%</strong></div><div><span>Expected value</span><strong>{checks.expected_value_r == null ? "—" : checks.expected_value_r.toFixed(2) + "R"}</strong></div></>
              : <div><span>{checks.calibration_note} Current sample: {checks.calibration_sample_size}/{checks.calibration_minimum_sample_size}.</span></div>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><h3>Hard invalidation gates</h3><span>Any failure here produces NO TRADE. These controls remain fail-closed.</span></div></div>
          <div className="enhanced-check-grid">
            {checks.evidence.filter(item => item.category === "hard_gate").map(item => <EvidenceRow key={item.key} item={item}/>)}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><h3>Execution quality factors</h3><span>These determine whether a valid context is ready now or remains in WAIT.</span></div></div>
          <div className="enhanced-check-grid">
            {checks.evidence.filter(item => item.category === "quality_factor").map(item => <EvidenceRow key={item.key} item={item}/>)}
          </div>
        </section>

        <section className="workspace-grid">
          <section className="panel">
            <div className="panel-head"><div><h3>Setup evidence</h3><span>{signal.symbol} · {signal.session ?? "Session unavailable"} · {signal.regime ?? "Regime unavailable"}</span></div></div>
            <div className="enhanced-evidence-list">{signal.evidence.map((item, index) => <details key={String(index) + "-" + item} className="enhanced-evidence-row"><summary><span>{item}</span></summary></details>)}</div>
          </section>
          <section className="panel">
            <div className="panel-head"><div><h3>Risk contract</h3><span>Guardrails are documented, not discretionary.</span></div></div>
            <div className="enhanced-risk-grid"><div><span>Risk / trade</span><strong>0.75%</strong></div><div><span>Max daily loss</span><strong>2.00%</strong></div><div><span>Correlated positions</span><strong>2 max</strong></div><div><span>Stop widening</span><strong>Never</strong></div><div><span>Averaging down</span><strong>Never</strong></div><div><span>Breakeven</span><strong>Not automated</strong></div></div>
          </section>
        </section>

        {(checks.hard_gate_failures.length > 0 || checks.quality_factor_failures.length > 0) && <section className="panel enhanced-failures">
          <h3>{checks.decision_status === "WAIT" ? "Why this setup is not ready" : "Why this is not a trade"}</h3>
          {checks.hard_gate_failures.map(reason => <div key={"hard-"+reason}><XCircle size={15}/><span>Hard gate: {reason.replaceAll("_", " ")}</span></div>)}
          {checks.quality_factor_failures.map(reason => <div key={"quality-"+reason}><XCircle size={15}/><span>Quality factor: {reason.replaceAll("_", " ")}</span></div>)}
        </section>}
        <footer>Research and decision support only. Enhanced Signal does not execute trades. Validate all market-data provenance and outcome records independently.</footer>
      </section>}
    </main></div>;
}