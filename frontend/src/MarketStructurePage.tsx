import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, getMarketStructure, getTechnicalAnalysis, MarketStructureResult, StructureEvent, TechnicalAnalysis, User } from "./api";
import "./market-structure.css";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
const TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"];
const EVENT_GROUPS = {
  Structure: ["SWING_HIGH", "SWING_LOW", "HIGHER_HIGH", "HIGHER_LOW", "LOWER_HIGH", "LOWER_LOW", "BOS_BULLISH", "BOS_BEARISH", "CHOCH_BULLISH", "CHOCH_BEARISH"],
  Liquidity: ["EQUAL_HIGH", "EQUAL_LOW", "LIQUIDITY_POOL_HIGH", "LIQUIDITY_POOL_LOW", "LIQUIDITY_SWEEP_HIGH", "LIQUIDITY_SWEEP_LOW", "STOP_RUN_HIGH", "STOP_RUN_LOW"],
  SMC: ["ORDER_BLOCK_BULLISH", "ORDER_BLOCK_BEARISH", "FVG_BULLISH", "FVG_BEARISH", "DISPLACEMENT_BULLISH", "DISPLACEMENT_BEARISH", "PREMIUM", "DISCOUNT", "INDUCEMENT_BULLISH", "INDUCEMENT_BEARISH"],
} as const;

type GroupName = keyof typeof EVENT_GROUPS;

function label(type: string): string { return type.replaceAll("_", " "); }
function groupFor(type: string): GroupName { if ((EVENT_GROUPS.Liquidity as readonly string[]).includes(type)) return "Liquidity"; if ((EVENT_GROUPS.SMC as readonly string[]).includes(type)) return "SMC"; return "Structure"; }
function fmtPrice(price: number): string { return price.toLocaleString(undefined, { maximumFractionDigits: 8 }); }
function fmtTime(value: string): string { const d = new Date(value); return Number.isNaN(d.getTime()) ? value : d.toLocaleString(undefined, { timeZone: "UTC", hour12: false }) + " UTC"; }

function EventBadge({ type }: { type: string }) { return <span className={`smc-badge smc-${groupFor(type).toLowerCase()}`}>{label(type)}</span>; }

function StructureChart({ analysis, events }: { analysis: TechnicalAnalysis; events: StructureEvent[] }) {
  const candles = analysis.candles.filter(c => c.is_complete).slice(-140);
  const width = 1100; const height = 460; const pad = { left: 58, right: 18, top: 20, bottom: 34 };
  if (candles.length < 2) return <div className="empty">Not enough completed candles to render the structure chart.</div>;
  const min = Math.min(...candles.map(c => c.low)); const max = Math.max(...candles.map(c => c.high)); const range = Math.max(max - min, Number.EPSILON);
  const x = (i: number) => pad.left + (i / (candles.length - 1)) * (width - pad.left - pad.right);
  const y = (price: number) => pad.top + ((max - price) / range) * (height - pad.top - pad.bottom);
  const firstTime = new Date(candles[0].timestamp).getTime(); const lastTime = new Date(candles[candles.length - 1].timestamp).getTime();
  const eventPoints = events.map(event => {
    const t = new Date(event.time).getTime();
    const ratio = lastTime === firstTime ? 0 : (t - firstTime) / (lastTime - firstTime);
    return { event, i: ratio * (candles.length - 1) };
  }).filter(p => p.i >= 0 && p.i <= candles.length - 1);
  const closePath = candles.map((c, i) => `${x(i)},${y(c.close)}`).join(" ");
  return <div className="smc-chart-wrap"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${analysis.symbol} ${analysis.timeframe} market structure chart`} className="smc-chart">
    {[0, .25, .5, .75, 1].map((v) => <line key={v} x1={pad.left} x2={width-pad.right} y1={y(max-range*v)} y2={y(max-range*v)} className="smc-grid-line"/>)}
    <polyline points={closePath} className="smc-close-line" fill="none" />
    {eventPoints.map(({ event, i }, n) => { const cx = x(i); const cy = y(event.price); const bullish = /BULLISH|HIGH|PREMIUM/.test(event.type); const above = /HIGH|PREMIUM|BEARISH/.test(event.type); const markerY = above ? cy - 10 : cy + 10; return <g key={`${event.time}-${event.type}-${n}`} className="smc-event-point"><line x1={cx} x2={cx} y1={cy} y2={markerY} className="smc-event-stem"/><circle cx={cx} cy={cy} r="4" className={bullish ? "smc-point-bull" : "smc-point-bear"}/><title>{label(event.type)} · {fmtPrice(event.price)} · {fmtTime(event.time)}</title></g>; })}
    <text x={pad.left} y={height-10} className="smc-axis-label">{fmtTime(candles[0].timestamp)}</text><text x={width-pad.right} y={height-10} textAnchor="end" className="smc-axis-label">{fmtTime(candles[candles.length-1].timestamp)}</text>
  </svg></div>;
}

export default function MarketStructurePage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (page: "market" | "watchlists" | "analysis" | "market-structure") => void }) {
  const [symbol, setSymbol] = useState(SYMBOLS[0]); const [timeframe, setTimeframe] = useState("1h");
  const [result, setResult] = useState<MarketStructureResult | null>(null); const [analysis, setAnalysis] = useState<TechnicalAnalysis | null>(null);
  const [loading, setLoading] = useState(true); const [refreshing, setRefreshing] = useState(false); const [error, setError] = useState<string | null>(null); const [activeGroup, setActiveGroup] = useState<GroupName | "ALL">("ALL");
  const load = useCallback(async (force = false) => { try { setError(null); force ? setRefreshing(true) : setLoading(true); const [structure, candles] = await Promise.all([getMarketStructure(symbol, timeframe, 250), getTechnicalAnalysis(symbol, timeframe, 250)]); setResult(structure); setAnalysis(candles); } catch (err) { if (err instanceof ApiError && err.status === 401) { onLogout(); return; } setError(err instanceof Error ? err.message : "Unable to retrieve Phase 6 market-structure research."); } finally { setLoading(false); setRefreshing(false); } }, [onLogout, symbol, timeframe]);
  useEffect(() => { void load(); }, [load]);
  const events = useMemo(() => result?.events.filter(e => activeGroup === "ALL" || groupFor(e.type) === activeGroup) ?? [], [activeGroup, result]);
  const counts = useMemo(() => Object.fromEntries((Object.keys(EVENT_GROUPS) as GroupName[]).map(group => [group, result?.events.filter(e => groupFor(e.type) === group).length ?? 0])) as Record<GroupName, number>, [result]);
  return <div className="app"><header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button" onClick={() => setPage("market")}>Market Data</button><button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button><button className="nav-button" onClick={() => setPage("analysis")}>Technical Analysis</button><button className="nav-button active" onClick={() => setPage("market-structure")}>Market Structure</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header><main>
    <section className="hero"><div><div className="eyebrow">Phase 6 · Market structure & SMC research</div><h2>Structure, liquidity and SMC events from completed candles.</h2><p>The visualization is a presentation layer over the Phase 6 API. It does not recalculate structure in the browser, and each event retains its detection timestamp and audit metadata.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>{result?.events.length ?? 0}</strong><span>detected events</span></div></section>
    <section className="ta-controls panel"><label>Instrument<select value={symbol} onChange={e => setSymbol(e.target.value)} disabled={loading || refreshing}>{SYMBOLS.map(s => <option key={s}>{s}</option>)}</select></label><label>Timeframe<select value={timeframe} onChange={e => setTimeframe(e.target.value)} disabled={loading || refreshing}>{TIMEFRAMES.map(s => <option key={s}>{s}</option>)}</select></label><button className="refresh" onClick={() => void load(true)} disabled={loading || refreshing}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh"}</button></section>
    {error && <div className="error" role="alert"><AlertTriangle size={17}/>{error}<button className="refresh" onClick={() => void load(true)}>Retry</button></div>}
    {loading ? <div className="panel empty" role="status">Loading Phase 6 structure and completed candles…</div> : result && analysis ? <>
      <section className="smc-summary-grid">{(Object.keys(EVENT_GROUPS) as GroupName[]).map(group => <button key={group} className={`panel smc-summary ${activeGroup === group ? "selected" : ""}`} onClick={() => setActiveGroup(group)}><span>{group}</span><strong>{counts[group]}</strong><small>events</small></button>)}</section>
      <section className="panel"><div className="panel-head"><div><h3>Structure map</h3><span>{result.symbol} · {result.timeframe} · {result.source} · latest completed candle {fmtTime(result.latest_candle_timestamp)}</span></div><ShieldCheck size={20}/></div><StructureChart analysis={analysis} events={result.events}/><div className="smc-legend"><span><i className="smc-dot bull"/>Bullish / upper structure</span><span><i className="smc-dot bear"/>Bearish / lower structure</span><span>Hover markers for event details</span></div></section>
      <section className="smc-two-col"><section className="panel"><div className="panel-head"><div><h3>Event stream</h3><span>{events.length} events · filter: {activeGroup}</span></div></div>{events.length === 0 ? <div className="empty">No events match this filter.</div> : <div className="smc-events">{events.slice().reverse().map((event, i) => <article className="smc-event" key={`${event.time}-${event.type}-${i}`}><div className="smc-event-head"><EventBadge type={event.type}/><strong>{fmtPrice(event.price)}</strong></div><div className="smc-event-meta"><span>{fmtTime(event.time)}</span><span>strength {(event.strength * 100).toFixed(0)}%</span><span>{event.status}</span></div><div className="smc-audit"><span>Invalidation: {event.invalidation == null ? "—" : fmtPrice(event.invalidation)}</span><span>Source candles: {event.source_candles.length}</span></div></article>)}</div>}</section>
      <section className="panel"><div className="panel-head"><div><h3>Research contract</h3><span>Phase 6 audit fields</span></div><ShieldCheck size={20}/></div><div className="metric-grid"><div><span>Symbol</span><strong>{result.symbol}</strong></div><div><span>Timeframe</span><strong>{result.timeframe}</strong></div><div><span>Candles</span><strong>{result.candle_count}</strong></div><div><span>Calculated</span><strong>{fmtTime(result.calculated_at)}</strong></div><div><span>Latest completed</span><strong>{fmtTime(result.latest_candle_timestamp)}</strong></div><div><span>Event groups</span><strong>Structure · Liquidity · SMC</strong></div></div><div className="smc-contract-note"><ShieldCheck size={16}/><span>Events are displayed using the API's <code>type</code>, <code>price</code>, <code>time</code>, <code>timeframe</code>, <code>strength</code>, <code>status</code>, <code>invalidation</code>, and <code>source_candles</code> fields.</span></div></section></section>
    </> : <div className="panel empty">No Phase 6 research is currently available.</div>}
    <footer>This tool provides market research and analysis assistance only. It is not financial advice, a recommendation to buy or sell, or a substitute for professional advice.</footer>
  </main></div>;
}
