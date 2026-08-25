import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, BarChart3, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, getTechnicalAnalysis, TechnicalAnalysis, User } from "./api";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
const TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"];

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

export default function TechnicalAnalysisPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (page: "market" | "watchlists" | "analysis") => void }) {
  const [symbol, setSymbol] = useState(SYMBOLS[0]);
  const [timeframe, setTimeframe] = useState("1h");
  const [data, setData] = useState<TechnicalAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (force = false) => {
    try {
      setError(null);
      force ? setRefreshing(true) : setLoading(true);
      setData(await getTechnicalAnalysis(symbol, timeframe));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { onLogout(); return; }
      setError(err instanceof Error ? err.message : "Unable to retrieve technical-analysis data.");
    } finally { setLoading(false); setRefreshing(false); }
  }, [onLogout, symbol, timeframe]);

  useEffect(() => { void load(); }, [load]);

  const trend = useMemo(() => typeof data?.indicators.trend === "string" ? data.indicators.trend : "UNKNOWN", [data]);
  const lastCompleted = useMemo(() => {
    if (!data) return undefined;
    return [...data.candles].reverse().find(candle => candle.is_complete);
  }, [data]);
  const rows = [
    ["EMA 20", value(data, "ema20")], ["EMA 50", value(data, "ema50")], ["EMA 200", value(data, "ema200")],
    ["SMA 20", value(data, "sma20")], ["SMA 50", value(data, "sma50")], ["SMA 200", value(data, "sma200")],
    ["RSI (14)", value(data, "rsi14", 2)], ["MACD", value(data, "macd", 5)], ["MACD signal", value(data, "macd_signal", 5)],
    ["ATR (14)", value(data, "atr14", 5)], ["ADX (14)", value(data, "adx14", 2)], ["Stochastic %K", value(data, "stochastic_k", 2)],
    ["Bollinger upper", value(data, "bb_upper")], ["Bollinger lower", value(data, "bb_lower")], ["Bollinger width", value(data, "bb_width", 5)],
    ["OBV", value(data, "obv", 2)], ["VWAP", value(data, "vwap")],
  ];

  return <div className="app"><header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button" onClick={() => setPage("market")}>Market Data</button><button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button><button className="nav-button active" onClick={() => setPage("analysis")}>Technical Analysis</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header><main>
    <section className="hero"><div><div className="eyebrow">Phase 3 · Technical analysis</div><h2>Deterministic indicators from canonical historical candles.</h2><p>Indicators are calculated server-side from provider-sourced OHLCV data. This phase reports technical facts; it does not generate trading signals.</p></div><div className="hero-stat"><BarChart3 size={20}/><strong>{data?.candle_count ?? 0}</strong><span>completed candles</span></div></section>
    <section className="ta-controls panel"><div><label>Instrument<select value={symbol} onChange={e => setSymbol(e.target.value)}>{SYMBOLS.map(item => <option key={item}>{item}</option>)}</select></label></div><div><label>Timeframe<select value={timeframe} onChange={e => setTimeframe(e.target.value)}>{TIMEFRAMES.map(item => <option key={item}>{item}</option>)}</select></label></div><button className="refresh" onClick={() => void load(true)} disabled={loading || refreshing}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh analysis"}</button></section>
    {error && <div className="error"><AlertTriangle size={17}/>{error}</div>}
    {loading ? <div className="panel empty">Loading historical candles and indicators…</div> : data && <><section className="ta-overview"><div className="panel"><div className="panel-head"><div><h3>{data.symbol} · {data.timeframe}</h3><span>Source: {data.source} · latest completed candle {formatTimestamp(data.latest_candle_timestamp)}</span></div><ShieldCheck size={20}/></div><div className="ta-price">{lastCompleted?.close.toLocaleString(undefined, { maximumFractionDigits: 8 }) ?? "—"}</div><div className={`large-status ${indicatorClass(trend)}`}><span className="dot"/>{trend}</div><div className="panel-head"><span>Calculated: {formatTimestamp(data.calculated_at)}</span><span>{data.candle_count} completed / {data.candles.length} returned</span></div></div><div className="panel"><div className="panel-head"><div><h3>Momentum & strength</h3><span>Calculated from the same completed candle series</span></div><Activity size={20}/></div><div className="metric-grid"><div><span>RSI (14)</span><strong>{value(data, "rsi14", 2)}</strong></div><div><span>ADX (14)</span><strong>{value(data, "adx14", 2)}</strong></div><div><span>MACD</span><strong>{value(data, "macd", 5)}</strong></div><div><span>ATR (14)</span><strong>{value(data, "atr14", 5)}</strong></div></div></div></section><section className="panel"><div className="panel-head"><div><h3>Indicator matrix</h3><span>Unavailable values are intentionally shown as — when history is insufficient.</span></div></div><div className="indicator-table">{rows.map(([name, result]) => <div className="indicator-row" key={name}><span>{name}</span><strong>{result}</strong></div>)}</div></section><section className="panel"><div className="panel-head"><div><h3>Recent candles</h3><span>Provider-sourced OHLCV observations · forming candles are excluded from indicator calculations.</span></div></div><div className="candle-table"><div className="candle-head"><span>Timestamp</span><span>Open</span><span>High</span><span>Low</span><span>Close</span><span>Volume</span></div>{data.candles.slice(-12).reverse().map(c => <div className="candle-row" key={c.timestamp}><span>{c.timestamp}{c.is_complete ? "" : " · forming"}</span><span>{c.open}</span><span>{c.high}</span><span>{c.low}</span><span>{c.close}</span><span>{c.volume ?? "—"}</span></div>)}</div></section></>}
    <footer>Technical analysis is informational research output. It is not financial advice or a trading recommendation.</footer>
  </main></div>;
}
