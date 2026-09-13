import { useEffect, useState } from "react";
import { getResearchReport, ResearchReport } from "./researchReportsApi";
import "./research-reports.css";

const ASSETS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
const money = (value: number | null) => value == null ? "Unavailable" : value >= 100 ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value.toLocaleString(undefined, { maximumFractionDigits: 6 });
const pct = (value: number | null) => value == null ? "Unavailable" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
const time = (value: string) => new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

function Metric({ label, value }: { label: string; value: string }) { return <div className="report-metric"><span>{label}</span><strong>{value}</strong></div>; }
function List({ items }: { items: string[] }) { return <ul>{items.length ? items.map(item => <li key={item}>{item}</li>) : <li>Unavailable from current validated data.</li>}</ul>; }

export default function ResearchReportsPage() {
  const [symbol, setSymbol] = useState("");
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async (requestedSymbol?: string) => {
    setLoading(true);
    setError(null);
    try {
      const nextReport = await getResearchReport(requestedSymbol || undefined);
      setReport(nextReport);
      setSymbol(nextReport.symbol);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate report.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void generate(); }, []);

  const config = report?.request_configuration;
  const hasTechnical = config?.technical_analysis ?? true;
  const hasStructure = config?.market_structure ?? true;
  const hasMtf = config?.multi_timeframe ?? true;
  const hasFundamental = config?.fundamental_analysis ?? true;
  const hasNews = config?.news_analysis ?? true;
  const hasAi = config?.ai_interpretation ?? true;

  return <section className="research-report-page">
    <div className="report-hero">
      <div>
        <div className="eyebrow">Phase 10 · Research Reports</div>
        <h1>{report?.symbol ?? symbol || "Personalized Market Research"}</h1>
        <p>Research requests use your saved Research Preferences. Enabled components are requested without changing the underlying analytical algorithms.</p>
      </div>
      <div className="report-controls">
        <label>Asset<select value={symbol} onChange={e => setSymbol(e.target.value)}>{ASSETS.map(asset => <option key={asset}>{asset}</option>)}</select></label>
        <button type="button" onClick={() => void generate(symbol)} disabled={loading}>{loading ? "Generating…" : "Generate report"}</button>
      </div>
    </div>

    {config && <div className="report-preference-bar">
      <span><strong>Personalized:</strong> {config.analysis_depth}</span>
      <span>Primary timeframe: <strong>{config.default_timeframe}</strong></span>
      <span>Technical {config.technical_analysis ? "ON" : "OFF"}</span>
      <span>Structure {config.market_structure ? "ON" : "OFF"}</span>
      <span>MTF {config.multi_timeframe ? "ON" : "OFF"}</span>
      <span>Fundamentals {config.fundamental_analysis ? "ON" : "OFF"}</span>
      <span>News {config.news_analysis ? "ON" : "OFF"}</span>
      <span>AI {config.ai_interpretation ? "ON" : "OFF"}</span>
    </div>}

    {error && <div className="report-error">{error}</div>}
    {report && <>
      <div className="report-grid status-grid">
        <Metric label="Current Price" value={money(report.market_status.current_price)} />
        <Metric label="24H Change" value={pct(report.market_status.change_24h_percent)} />
        <Metric label="Volume" value={money(report.market_status.volume)} />
        {hasTechnical && <Metric label="Volatility" value={report.market_status.volatility_percent == null ? "Unavailable" : `${report.market_status.volatility_percent.toFixed(2)}% ATR`} />}
        {hasTechnical && <Metric label="Trend" value={report.market_status.trend} />}
        {hasTechnical && <Metric label="Momentum" value={report.market_status.momentum} />}
        {hasStructure && <Metric label="Support" value={money(report.market_status.support)} />}
        {hasStructure && <Metric label="Resistance" value={money(report.market_status.resistance)} />}
        {hasTechnical && <Metric label="Market Regime" value={report.market_status.market_regime} />}
        {hasStructure && <Metric label="Technical Structure" value={report.market_status.technical_structure} />}
      </div>

      {hasStructure && <div className="report-section"><h2>SMC Structure</h2><div className="smc-grid"><Metric label="BOS" value={report.smc_structure.bos ?? "None detected"} /><div><h3>FVG</h3><List items={report.smc_structure.fvg} /></div><div><h3>Order Blocks</h3><List items={report.smc_structure.order_blocks} /></div><div><h3>Liquidity</h3><List items={report.smc_structure.liquidity} /></div></div></div>}

      {hasMtf && <div className="report-section"><h2>Multi-Timeframe</h2><div className="mtf-table"><div className="mtf-head"><span>Timeframe</span><span>Trend</span><span>Momentum</span><span>Regime</span><span>Support</span><span>Resistance</span></div>{report.multi_timeframe.map(item => <div className="mtf-row" key={item.timeframe}><strong>{item.timeframe}</strong><span>{item.trend}</span><span>{item.momentum}</span><span>{item.regime}</span><span>{money(item.support)}</span><span>{money(item.resistance)}</span></div>)}</div></div>}

      {(hasFundamental || hasNews) && <div className="report-section"><h2>Fundamental &amp; News Context</h2><div className="report-grid">{hasNews && <Metric label="News" value={String(report.fundamental_context.news_count)} />}{hasFundamental && <Metric label="Macro" value={String(report.fundamental_context.macro_count)} />}{hasFundamental && <Metric label="Events" value={String(report.fundamental_context.event_count)} />}</div>{hasNews && <div className="headlines"><h3>Recent headlines</h3><List items={report.fundamental_context.headlines} /></div>}</div>}

      {hasAi && report.ai_interpretation && <div className="report-section"><h2>AI Interpretation</h2><p className="interpretation">{report.ai_interpretation}</p></div>}
      <div className="report-columns"><div className="report-section"><h2>Bull Case</h2><List items={report.bull_case} /></div><div className="report-section"><h2>Bear Case</h2><List items={report.bear_case} /></div></div>
      <div className="report-columns"><div className="report-section"><h2>Key Risks</h2><List items={report.key_risks} /></div><div className="report-section"><h2>Invalidation</h2><List items={report.invalidation} /></div></div>
      <div className="score-card"><div><div className="eyebrow">Overall Research Score</div><strong>{report.overall_research_score} <small>/ 100</small></strong><p>Deterministic composite of requested technical evidence. Not a probability of profit.</p></div><div className="score-basis">{Object.entries(report.score_basis).map(([key, value]) => <Metric key={key} label={key.replaceAll("_", " ")} value={value.toFixed(0)} />)}</div></div>
      <footer className="report-footer">Generated {time(report.generated_at)} · Research only · No trade is executed by this report. Information is for research purposes and is not financial advice.</footer>
    </>}
  </section>;
}
