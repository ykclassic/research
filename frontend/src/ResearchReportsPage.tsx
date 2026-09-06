import { useEffect, useState } from "react";
import { getResearchReport, ResearchReport } from "./researchReportsApi";
import "./research-reports.css";

const ASSETS = ["BTC/USD", "ETH/USD", "EUR/USD", "GBP/USD", "XAU/USD", "AAPL"];
const money = (value: number | null) => value == null ? "Unavailable" : value >= 100 ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value.toLocaleString(undefined, { maximumFractionDigits: 6 });
const pct = (value: number | null) => value == null ? "Unavailable" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
const time = (value: string) => new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

function Metric({ label, value }: { label: string; value: string }) { return <div className="report-metric"><span>{label}</span><strong>{value}</strong></div>; }
function List({ items }: { items: string[] }) { return <ul>{items.length ? items.map(item => <li key={item}>{item}</li>) : <li>Unavailable from current validated data.</li>}</ul>; }

export default function ResearchReportsPage() {
  const [symbol, setSymbol] = useState(ASSETS[0]);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generate = async () => { setLoading(true); setError(null); try { setReport(await getResearchReport(symbol)); } catch (err) { setError(err instanceof Error ? err.message : "Unable to generate report."); } finally { setLoading(false); } };
  useEffect(() => { void generate(); }, []);

  return <section className="research-report-page">
    <div className="report-hero"><div><div className="eyebrow">Phase 10 · Research Reports</div><h1>{report?.symbol ?? symbol} Market Research</h1><p>Deterministic market evidence assembled into a complete research report. Fundamental context is evidence, not a causal prediction.</p></div><div className="report-controls"><label>Asset<select value={symbol} onChange={e => setSymbol(e.target.value)}>{ASSETS.map(asset => <option key={asset}>{asset}</option>)}</select></label><button type="button" onClick={() => void generate()} disabled={loading}>{loading ? "Generating…" : "Generate report"}</button></div></div>
    {error && <div className="report-error">{error}</div>}
    {report && <>
      <div className="report-grid status-grid">
        <Metric label="Current Price" value={money(report.market_status.current_price)} />
        <Metric label="24H Change" value={pct(report.market_status.change_24h_percent)} />
        <Metric label="Volume" value={money(report.market_status.volume)} />
        <Metric label="Volatility" value={report.market_status.volatility_percent == null ? "Unavailable" : `${report.market_status.volatility_percent.toFixed(2)}% ATR`} />
        <Metric label="Trend" value={report.market_status.trend} />
        <Metric label="Momentum" value={report.market_status.momentum} />
        <Metric label="Support" value={money(report.market_status.support)} />
        <Metric label="Resistance" value={money(report.market_status.resistance)} />
        <Metric label="Market Regime" value={report.market_status.market_regime} />
        <Metric label="Technical Structure" value={report.market_status.technical_structure} />
      </div>
      <div className="report-section"><h2>SMC Structure</h2><div className="smc-grid"><Metric label="BOS" value={report.smc_structure.bos ?? "None detected"} /><div><h3>FVG</h3><List items={report.smc_structure.fvg} /></div><div><h3>Order Blocks</h3><List items={report.smc_structure.order_blocks} /></div><div><h3>Liquidity</h3><List items={report.smc_structure.liquidity} /></div></div></div>
      <div className="report-section"><h2>Multi-Timeframe</h2><div className="mtf-table"><div className="mtf-head"><span>Timeframe</span><span>Trend</span><span>Momentum</span><span>Regime</span><span>Support</span><span>Resistance</span></div>{report.multi_timeframe.map(item => <div className="mtf-row" key={item.timeframe}><strong>{item.timeframe}</strong><span>{item.trend}</span><span>{item.momentum}</span><span>{item.regime}</span><span>{money(item.support)}</span><span>{money(item.resistance)}</span></div>)}</div></div>
      <div className="report-section"><h2>Fundamental Context</h2><div className="report-grid"><Metric label="News" value={String(report.fundamental_context.news_count)} /><Metric label="Macro" value={String(report.fundamental_context.macro_count)} /><Metric label="Events" value={String(report.fundamental_context.event_count)} /></div><div className="headlines"><h3>Recent headlines</h3><List items={report.fundamental_context.headlines} /></div></div>
      <div className="report-section"><h2>AI Interpretation</h2><p className="interpretation">{report.ai_interpretation}</p></div>
      <div className="report-columns"><div className="report-section"><h2>Bull Case</h2><List items={report.bull_case} /></div><div className="report-section"><h2>Bear Case</h2><List items={report.bear_case} /></div></div>
      <div className="report-columns"><div className="report-section"><h2>Key Risks</h2><List items={report.key_risks} /></div><div className="report-section"><h2>Invalidation</h2><List items={report.invalidation} /></div></div>
      <div className="score-card"><div><div className="eyebrow">Overall Research Score</div><strong>{report.overall_research_score} <small>/ 100</small></strong><p>Deterministic composite of trend, momentum, regime and multi-timeframe structure. Not a probability of profit.</p></div><div className="score-basis">{Object.entries(report.score_basis).map(([key, value]) => <Metric key={key} label={key.replaceAll("_", " ")} value={value.toFixed(0)} />)}</div></div>
      <footer className="report-footer">Generated {time(report.generated_at)} · Research only · No trade is executed by this report.</footer>
    </>}
  </section>;
}
