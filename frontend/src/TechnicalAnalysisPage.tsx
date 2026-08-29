import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, BarChart3, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, getTechnicalAnalysis, TechnicalAnalysis, TechnicalAnalysisRange, User } from "./api";
import TechnicalChart from "./chart/TechnicalChart";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
const TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"];
const ANALYSIS_REFRESH_MS = 60_000;

type RangePreset = "recent" | "1d" | "1w" | "1m" | "3m" | "custom";

export function toUtcStart(date: string): string { return `${date}T00:00:00Z`; }
export function toUtcEnd(date: string): string { return `${date}T23:59:59Z`; }

export function buildRange(preset: RangePreset, now = new Date(), customStart = "", customEnd = ""): TechnicalAnalysisRange {
  if (preset === "recent") return {};
  if (preset === "custom") {
    if (!customStart || !customEnd) return {};
    return { startDate: toUtcStart(customStart), endDate: toUtcEnd(customEnd) };
  }
  const end = new Date(now);
  end.setUTCHours(23, 59, 59, 0);
  const start = new Date(end);
  const days = preset === "1d" ? 1 : preset === "1w" ? 7 : preset === "1m" ? 30 : 90;
  start.setUTCDate(start.getUTCDate() - days + 1);
  return { startDate: start.toISOString(), endDate: end.toISOString() };
}

function value(data: TechnicalAnalysis | null, key: string, digits = 4): string {
  const raw = data?.indicators[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
}
function indicatorClass(trend: string | undefined): string { return trend === "BULLISH" ? "live" : trend === "BEARISH" ? "unavailable" : "closed"; }
function formatTimestamp(timestamp: string | undefined): string {
  if (!timestamp) return "—";
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString(undefined, { timeZone: "UTC", hour12: false }) + " UTC";
}
function validateAnalysisResponse(data: TechnicalAnalysis, requestedSymbol: string, requestedTimeframe: string): TechnicalAnalysis {
  if (data.symbol !== requestedSymbol) throw new Error(`The API returned analysis for ${data.symbol} instead of ${requestedSymbol}.`);
  if (data.timeframe !== requestedTimeframe) throw new Error(`The API returned timeframe ${data.timeframe} instead of ${requestedTimeframe}.`);
  if (!Array.isArray(data.candles) || data.candles.length === 0) throw new Error("The API returned no historical candles for this analysis.");
  if (!Number.isInteger(data.candle_count) || data.candle_count < 0 || data.candle_count > data.candles.length) throw new Error("The API returned an invalid completed-candle count.");
  if (!data.source || !data.calculated_at || !data.latest_candle_timestamp) throw new Error("The API returned incomplete analysis provenance metadata.");
  return data;
}

export default function TechnicalAnalysisPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (page: "market" | "watchlists" | "analysis") => void }) {
  const [symbol, setSymbol] = useState(SYMBOLS[0]);
  const [timeframe, setTimeframe] = useState("1h");
  const [rangePreset, setRangePreset] = useState<RangePreset>("recent");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [data, setData] = useState<TechnicalAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);
  const inFlightKey = useRef<string | null>(null);
  const hasDataRef = useRef(false);

  useEffect(() => { hasDataRef.current = Boolean(data); }, [data]);

  const range = useMemo(() => buildRange(rangePreset, new Date(), customStart, customEnd), [rangePreset, customStart, customEnd]);
  const rangeInvalid = rangePreset === "custom" && ((!customStart && !!customEnd) || (!!customStart && !customEnd) || (!!customStart && !!customEnd && customStart > customEnd));
  const requestKey = useMemo(() => JSON.stringify({ symbol, timeframe, range }), [symbol, timeframe, range]);

  const load = useCallback(async (force = false) => {
    if (rangeInvalid) {
      setError(customStart > customEnd ? "The range start must be on or before the range end." : "Select both a range start and range end before loading historical data.");
      return;
    }
    if (!force && inFlightKey.current === requestKey) return;
    const sequence = ++requestSequence.current;
    inFlightKey.current = requestKey;
    try {
      setError(null);
      if (!hasDataRef.current) setLoading(true);
      if (force) setRefreshing(true);
      const response = await getTechnicalAnalysis(symbol, timeframe, 250, range);
      const validated = validateAnalysisResponse(response, symbol, timeframe);
      if (sequence === requestSequence.current) setData(validated);
    } catch (err) {
      if (sequence !== requestSequence.current) return;
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to retrieve technical-analysis data.");
      if (!hasDataRef.current) setData(null);
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false);
        setRefreshing(false);
        inFlightKey.current = null;
      }
    }
  }, [customEnd, customStart, onLogout, range, rangeInvalid, requestKey, symbol, timeframe]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!autoRefresh || rangeInvalid) return;
    const timer = window.setInterval(() => void load(true), ANALYSIS_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [autoRefresh, load, rangeInvalid]);

  const trend = useMemo(() => typeof data?.indicators.trend === "string" ? data.indicators.trend : "UNKNOWN", [data]);
  const completedCandles = useMemo(() => data?.candles.filter(candle => candle.is_complete) ?? [], [data]);
  const lastCompleted = completedCandles[completedCandles.length - 1];
  const rows = [
    ["EMA 20", value(data, "ema20")], ["EMA 50", value(data, "ema50")], ["EMA 200", value(data, "ema200")],
    ["SMA 20", value(data, "sma20")], ["SMA 50", value(data, "sma50")], ["SMA 200", value(data, "sma200")],
    ["RSI (14)", value(data, "rsi14", 2)], ["MACD", value(data, "macd", 5)], ["MACD signal", value(data, "macd_signal", 5)],
    ["ATR (14)", value(data, "atr14", 5)], ["ADX (14)", value(data, "adx14", 2)], ["Stochastic %K", value(data, "stochastic_k", 2)],
    ["Bollinger upper", value(data, "bb_upper")], ["Bollinger lower", value(data, "bb_lower")], ["Bollinger width", value(data, "bb_width", 5)],
    ["OBV", value(data, "obv", 2)], ["VWAP", value(data, "vwap")],
  ];

  return <div className="app"><header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button" onClick={() => setPage("market")}>Market Data</button><button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button><button className="nav-button active" onClick={() => setPage("analysis")}>Technical Analysis</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header><main>
    <section className="hero"><div><div className="eyebrow">Phase 4 · Charting architecture</div><h2>Interactive financial charts backed by the verified technical-analysis API.</h2><p>The browser renders only completed provider-sourced candles returned by the canonical API. Range controls request new server-side data; no browser-side market filtering or fallback prices are used.</p></div><div className="hero-stat"><BarChart3 size={20}/><strong>{data?.candle_count ?? 0}</strong><span>completed candles</span></div></section>
    <section className="ta-controls panel"><div><label>Instrument<select value={symbol} onChange={e => setSymbol(e.target.value)} disabled={loading || refreshing}>{SYMBOLS.map(item => <option key={item}>{item}</option>)}</select></label></div><div><label>Timeframe<select value={timeframe} onChange={e => setTimeframe(e.target.value)} disabled={loading || refreshing}>{TIMEFRAMES.map(item => <option key={item}>{item}</option>)}</select></label></div><div><label>Historical range<select value={rangePreset} onChange={e => setRangePreset(e.target.value as RangePreset)} disabled={loading || refreshing}><option value="recent">Recent API window</option><option value="1d">1 day</option><option value="1w">1 week</option><option value="1m">1 month</option><option value="3m">3 months</option><option value="custom">Custom</option></select></label></div><label className="chart-date-field">Start<input type="date" value={customStart} onChange={e => { setCustomStart(e.target.value); setRangePreset("custom"); }} disabled={loading || refreshing || rangePreset !== "custom"}/></label><label className="chart-date-field">End<input type="date" value={customEnd} onChange={e => { setCustomEnd(e.target.value); setRangePreset("custom"); }} disabled={loading || refreshing || rangePreset !== "custom"}/></label><label className="chart-auto-refresh"><input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)}/> Auto-refresh (60s)</label><button className="refresh" onClick={() => void load(true)} disabled={loading || refreshing || rangeInvalid}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh"}</button></section>
    {rangeInvalid && <div className="error" role="alert"><AlertTriangle size={17}/>{customStart > customEnd ? "The range start must be on or before the range end." : "Select both a range start and range end."}</div>}
    {error && !rangeInvalid && <div className="error" role="alert"><AlertTriangle size={17}/>{error}<button className="refresh" onClick={() => void load(true)} disabled={refreshing}>Retry</button></div>}
    {loading ? <div className="panel empty" role="status">Loading historical candles and indicators from the canonical API…</div> : !data && !error ? <div className="panel empty">No analysis is currently available.</div> : data && <><section className="ta-overview"><div className="panel"><div className="panel-head"><div><h3>{data.symbol} · {data.timeframe}</h3><span>Source: {data.source} · latest completed candle {formatTimestamp(data.latest_candle_timestamp)}</span></div><ShieldCheck size={20}/></div><div className="ta-price">{lastCompleted?.close.toLocaleString(undefined, { maximumFractionDigits: 8 }) ?? "—"}</div><div className={`large-status ${indicatorClass(trend)}`}><span className="dot"/>{trend}</div><div className="panel-head"><span>API calculated: {formatTimestamp(data.calculated_at)}</span><span>{completedCandles.length} completed / {data.candles.length} returned</span></div></div><div className="panel"><div className="panel-head"><div><h3>Data provenance</h3><span>Historical market data remains authoritative at the API boundary.</span></div><ShieldCheck size={20}/></div><div className="metric-grid"><div><span>Data source</span><strong>{data.source}</strong></div><div><span>Latest candle</span><strong>{formatTimestamp(data.latest_candle_timestamp)}</strong></div><div><span>Request mode</span><strong>{rangePreset === "recent" ? "Recent window" : "Server range"}</strong></div><div><span>Auto-refresh</span><strong>{autoRefresh ? "60s" : "Off"}</strong></div></div></div></section><section className="panel chart-panel"><div className="panel-head"><div><h3>Market chart</h3><span>Canonical API OHLCV · synchronized candle/volume time scale · crosshair, zoom and pan preserve data synchronization.</span></div></div><TechnicalChart data={data}/></section><section className="panel"><div className="panel-head"><div><h3>Indicator matrix</h3><span>Unavailable values are intentionally shown as — when history is insufficient.</span></div></div><div className="indicator-table">{rows.map(([name, result]) => <div className="indicator-row" key={name}><span>{name}</span><strong>{result}</strong></div>)}</div></section><section className="panel"><div className="panel-head"><div><h3>Recent candles</h3><span>Provider-sourced OHLCV observations · forming candles are excluded from chart and indicator calculations.</span></div></div><div className="candle-table"><div className="candle-head"><span>Timestamp</span><span>Open</span><span>High</span><span>Low</span><span>Close</span><span>Volume</span></div>{data.candles.slice(-12).reverse().map(c => <div className="candle-row" key={c.timestamp}><span>{c.timestamp}{c.is_complete ? "" : " · forming"}</span><span>{c.open}</span><span>{c.high}</span><span>{c.low}</span><span>{c.close}</span><span>{c.volume ?? "—"}</span></div>)}</div></section></>}
    <footer>Technical analysis is informational research output. It is not financial advice or a trading recommendation.</footer>
  </main></div>;
}
