import { FormEvent, useEffect, useState } from "react";
import { AlertTriangle, Brain, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { ApiError, User, createAIResearchReport } from "./api";
import { getPreferences, AIPreferences } from "./settingsApi";
import { MarkdownReport } from "./MarkdownReport";
import "./ai-research.css";

type AppPage = "market" | "watchlists" | "analysis" | "market-structure" | "mtf" | "signals" | "ai-research";
interface Props { user: User; onLogout: () => void; setPage: (page: AppPage) => void; }
const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];

const DEFAULT_AI_PREFERENCES: AIPreferences = {
  enabled: true,
  analysis_style: "Analytical",
  interpretation_risk: "Balanced",
  require_evidence: true,
  show_confidence_scores: true,
  show_supporting_indicators: true,
  show_conflicting_evidence: true,
  output_sections: {
    executive_summary: true,
    technical_outlook: true,
    fundamental_outlook: true,
    news_impact: true,
    market_regime: true,
    bull_scenario: true,
    base_scenario: true,
    bear_scenario: true,
    key_risks: true,
    catalysts: true,
    invalidations: true,
  },
};

export default function AIResearchPage({ user, onLogout, setPage }: Props) {
  const [symbol, setSymbol] = useState("BTC/USD");
  const [question, setQuestion] = useState("");
  const [report, setReport] = useState<string | null>(null);
  const [context, setContext] = useState<Record<string, unknown> | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<AIPreferences>(DEFAULT_AI_PREFERENCES);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [preferencesError, setPreferencesError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getPreferences()
      .then(value => { if (active) { setPreferences(value.ai_preferences); setPreferencesLoaded(true); } })
      .catch(err => { if (active) { setPreferencesError(err instanceof Error ? err.message : "Unable to load AI preferences."); setPreferencesLoaded(true); } });
    return () => { active = false; };
  }, []);

  const generate = async (event: FormEvent) => {
    event.preventDefault();
    if (!preferences.enabled) {
      setError("AI research is disabled in Settings.");
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const result = await createAIResearchReport(symbol, "1h", 250, question.trim() || undefined);
      setReport(result.report);
      setContext(result.verified_context);
      setModel(result.model);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to generate AI market research.");
    } finally {
      setBusy(false);
    }
  };

  const evidence = Array.isArray(context?.evidence) ? context.evidence as Array<Record<string, unknown>> : [];
  const regimeEvidence = evidence.find(item => item.id === "REGIME");
  const mtfEvidence = evidence.find(item => item.id === "MTF");
  const confidenceValues = [regimeEvidence?.confidence, (mtfEvidence?.research as Record<string, unknown> | undefined)?.confidence]
    .filter((value): value is number => typeof value === "number");

  return <div className="app">
    <header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections">{(["market", "watchlists", "analysis", "market-structure", "mtf", "signals", "ai-research"] as const).map(page => <button key={page} className={`nav-button ${page === "ai-research" ? "active" : ""}`} onClick={() => setPage(page)}>{page === "ai-research" ? "AI Market Research" : page === "market" ? "Market Data" : page === "watchlists" ? "Watchlists" : page === "analysis" ? "Technical Analysis" : page === "market-structure" ? "Market Structure" : page === "mtf" ? "MTF Analysis" : "Signals"}</button>)}</nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header>
    <main><section className="hero ai-hero"><div><div className="eyebrow">Phase 8 · AI interpretation</div><h2>AI interprets verified research. It does not create market truth.</h2><p>The deterministic market-data, feature, regime, structure and multi-timeframe layers run first. S6 controls how the verified evidence is interpreted and presented; it cannot change those layers.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>GATED</strong><span>deterministic-first</span></div></section>
      {preferencesError && <div className="error"><AlertTriangle size={17}/>{preferencesError}</div>}
      {error && <div className="error"><AlertTriangle size={17}/>{error}</div>}
      <section className="panel" aria-label="AI presentation policy"><div className="panel-head"><div><h3>AI presentation policy</h3><span>Loaded from your Settings</span></div><Brain size={20}/></div><div className="evidence-grid"><div className="evidence-card"><strong>{preferences.enabled ? "ON" : "OFF"}</strong><span>AI research</span><small>{preferencesLoaded ? "Server-enforced preference" : "Loading preference…"}</small></div><div className="evidence-card"><strong>{preferences.analysis_style}</strong><span>Analysis style</span><small>{preferences.interpretation_risk} interpretation</small></div><div className="evidence-card"><strong>{preferences.require_evidence ? "Required" : "Guided"}</strong><span>Evidence mode</span><small>Deterministic gate remains mandatory</small></div>{preferences.show_confidence_scores && confidenceValues.length > 0 && <div className="evidence-card"><strong>{Math.round(Math.max(...confidenceValues) * 100)}%</strong><span>Verified confidence</span><small>Displayed because confidence scores are enabled</small></div>}</div></section>
      <section className="ai-grid"><form className="panel ai-request" onSubmit={generate}><div className="panel-head"><div><h3>Research request</h3><span>AI is unavailable until the deterministic gate passes.</span></div><Brain size={20}/></div><label>Asset<select value={symbol} onChange={e => setSymbol(e.target.value)} disabled={busy || !preferences.enabled}>{SYMBOLS.map(item => <option key={item}>{item}</option>)}</select></label><label>Research question <span className="optional">optional</span><textarea value={question} onChange={e => setQuestion(e.target.value)} maxLength={2000} placeholder="Example: Explain the current trend/structure confluence and the main conflicts." disabled={busy || !preferences.enabled}/></label><button className="ai-generate" type="submit" disabled={busy || !preferences.enabled}>{busy ? <><Loader2 size={16} className="spin"/>Running deterministic gate…</> : <><Brain size={16}/>{preferences.enabled ? "Generate verified interpretation" : "AI research disabled in Settings"}</>}</button><div className="ai-policy"><CheckCircle2 size={16}/><span>AI cannot write prices, timestamps, indicators, candles, market status, or calculated statistics into the verified data layer.</span></div></form>
        <section className="panel ai-report"><div className="panel-head"><div><h3>Human-readable report</h3><span>{model ? `Generated by ${model}` : "No report generated"}</span></div><Brain size={20}/></div>{report ? <article className="report-body"><MarkdownReport markdown={report} /></article> : <div className="empty">{preferences.enabled ? "Choose an asset and generate a report. The server will first validate deterministic research eligibility." : "Enable AI research in Settings to generate an interpretation."}</div>}</section></section>
      {context && <section className="panel verified-context"><div className="panel-head"><div><h3>Verified research context</h3><span>Server-generated evidence supplied to the AI layer</span></div><ShieldCheck size={20}/></div><div className="evidence-grid">{evidence.map(item => <div className="evidence-card" key={String(item.id)}><strong>{String(item.id)}</strong><span>{String(item.type).replaceAll("_", " ")}</span><small>{String(item.latest_candle_timestamp ?? item.calculated_at ?? "Verified deterministic result")}</small></div>)}</div>{preferences.show_confidence_scores && confidenceValues.length > 0 && <div className="ai-warning"><CheckCircle2 size={16}/><span>Confidence presentation is enabled. The displayed values come from deterministic model output; the AI does not calculate or modify them.</span></div>}{preferences.show_supporting_indicators && <div className="ai-warning"><CheckCircle2 size={16}/><span>Supporting deterministic indicators are available to the AI interpretation layer.</span></div>}{preferences.show_conflicting_evidence && <div className="ai-warning"><AlertTriangle size={16}/><span>Conflicting-evidence presentation is enabled. The AI is instructed to surface material conflicts rather than resolve them by invention.</span></div>}<div className="ai-warning"><AlertTriangle size={16}/><span>The values shown here remain authoritative only in the deterministic layer. AI prose is an interpretation, not a replacement for these verified results.</span></div></section>}
      <footer>This tool provides market research and analysis assistance only. It is not financial advice, a recommendation to buy or sell, or a substitute for professional advice.</footer></main></div>;
}
