import { FormEvent, useEffect, useState } from "react";
import { AlertTriangle, Brain, CheckCircle2, Clock3, Loader2, ShieldCheck } from "lucide-react";
import { ApiError, ResearchCopilotResult, User, getResearchCopilotHistory, runResearchCopilot } from "./api";
import { MarkdownReport } from "./MarkdownReport";
import "./ai-research.css";

type AppPage = "market" | "watchlists" | "analysis" | "market-structure" | "mtf" | "signals" | "ai-research";
interface Props { user: User; onLogout: () => void; setPage: (page: AppPage) => void; }

const EXAMPLES = [
  "Compare BTC/USD and ETH/USD over the last 30 days.",
  "What changed since yesterday?",
  "Why did BTC/USD's signal quality deteriorate?",
  "Show me the evidence behind this conclusion.",
  "Find historical setups similar to this one.",
];

export default function AIResearchPage({ user, onLogout, setPage }: Props) {
  const [question, setQuestion] = useState(EXAMPLES[0]);
  const [result, setResult] = useState<ResearchCopilotResult | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getResearchCopilotHistory().then(setHistory).catch(() => undefined);
  }, []);

  const run = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const next = await runResearchCopilot(question.trim());
      setResult(next);
      setHistory(current => [{ id: next.run_id, query: next.query, generated_report: next.report, created_at: next.timestamp }, ...current].slice(0, 20));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to run grounded research.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="app">
    <header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Research Copilot</h1></div><nav className="main-nav" aria-label="Research sections">{(["market", "watchlists", "analysis", "market-structure", "mtf", "signals", "ai-research"] as const).map(page => <button key={page} className={`nav-button ${page === "ai-research" ? "active" : ""}`} onClick={() => setPage(page)}>{page === "ai-research" ? "Research Copilot" : page === "market" ? "Market Data" : page === "watchlists" ? "Watchlists" : page === "analysis" ? "Technical Analysis" : page === "market-structure" ? "Market Structure" : page === "mtf" ? "MTF Analysis" : "Signals"}</button>)}</nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header>
    <main>
      <section className="hero ai-hero"><div><div className="eyebrow">Phase 5 · Grounded AI Research</div><h2>Ask questions. Get answers tied to platform evidence.</h2><p>The Copilot interprets your question, retrieves structured research, then synthesizes it. It cannot create market facts outside the verified evidence layer.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>GROUNDED</strong><span>evidence-first</span></div></section>
      {error && <div className="error"><AlertTriangle size={17}/>{error}</div>}
      <section className="panel"><div className="panel-head"><div><h3>Research question</h3><span>Natural language is converted into a structured research run.</span></div><Brain size={20}/></div>
        <form className="ai-request" onSubmit={run}>
          <textarea value={question} onChange={e => setQuestion(e.target.value)} maxLength={4000} rows={4} disabled={busy} aria-label="Research question"/>
          <div className="copilot-examples">{EXAMPLES.map(example => <button type="button" key={example} onClick={() => setQuestion(example)} disabled={busy}>{example}</button>)}</div>
          <button className="ai-generate" type="submit" disabled={busy || !question.trim()}>{busy ? <><Loader2 size={16} className="spin"/>Retrieving evidence…</> : <><Brain size={16}/>Run grounded research</>}</button>
        </form>
      </section>

      {result && <><section className="panel"><div className="panel-head"><div><h3>Research answer</h3><span>Run {result.run_id} · {result.model_version}</span></div><CheckCircle2 size={20}/></div>
        <article className="report-body"><MarkdownReport markdown={result.report}/></article>
      </section>
      <section className="panel verified-context"><div className="panel-head"><div><h3>Evidence & methodology</h3><span>Every material answer is linked to deterministic evidence.</span></div><ShieldCheck size={20}/></div>
        <div className="evidence-grid">{result.evidence.map(item => <div className="evidence-card" key={item.id}><strong>{item.id}</strong><span>{item.claim}</span><small>{item.asset ?? "Platform"} · {new Date(item.timestamp).toLocaleString()}</small><small>{item.methodology}</small>{typeof item.confidence === "number" && <small>Confidence: {Math.round(item.confidence * 100)}%</small>}</div>)}</div>
        <div className="ai-warning"><CheckCircle2 size={16}/><span><strong>Method:</strong> {result.methodology}</span></div>
        {result.sources.map((source, index) => <div className="ai-warning" key={index}><Clock3 size={16}/><span>{String(source.source ?? "Platform source")} · {String(source.timestamp ?? "Timestamp unavailable")}</span></div>)}
        <div className="ai-warning"><AlertTriangle size={16}/><span><strong>Limitations:</strong> {result.limitations.join(" ")}</span></div>
      </section></>}

      <section className="panel"><div className="panel-head"><div><h3>Research run history</h3><span>Persistent, reproducible Copilot runs.</span></div><Clock3 size={20}/></div>
        {!history.length ? <div className="empty">No Copilot runs yet.</div> : <div className="history-list">{history.map(item => <div className="history-row" key={String(item.id)}><strong>{String(item.query ?? "Research run")}</strong><span>{item.created_at ? new Date(String(item.created_at)).toLocaleString() : "—"}</span></div>)}</div>}
      </section>
      <footer>Research and decision support only. AI interpretation does not replace deterministic market calculations or provide autonomous trading instructions.</footer>
    </main>
  </div>;
}
