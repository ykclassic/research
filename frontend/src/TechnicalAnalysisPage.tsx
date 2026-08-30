import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, BarChart3, RefreshCw, ShieldCheck } from "lucide-react";
import { ApiError, getTechnicalAnalysis, TechnicalAnalysis, User } from "./api";
import TechnicalChart from "./chart/TechnicalChart";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
const TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"];
const ANALYSIS_REFRESH_MS = 60_000;

function value(data: TechnicalAnalysis | null, key: string, digits = 4): string {
  const raw = data?.indicators[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
}

function indicatorClass(trend: string | undefined): string {
  return trend === "BULLISH" ? "live" : trend === "BEARISH" ? "unavailable" : "closed";
}

function formatTimestamp(timestamp: string | undefined): string {
  if (!timestamp) return "—";
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime())
    ? timestamp
    : parsed.toLocaleString(undefined, { timeZone: "UTC", hour12: false }) + " UTC";
}

function validateAnalysisResponse(data: TechnicalAnalysis, requestedSymbol: string, requestedTimeframe: string): TechnicalAnalysis {
  if (data.symbol !== requestedSymbol) {
    throw new Error(`The API returned analysis for ${data.symbol} instead of ${requestedSymbol}.`);
  }
  if (data.timeframe !== requestedTimeframe) {
    throw new Error(`The API returned timeframe ${data.timeframe} instead of ${requestedTimeframe}.`);
  }
  if (!Array.isArray(data.candles) || data.candles.length === 0) {
    throw new Error("The API returned no historical candles for this analysis.");
  }
  if (!Number.isInteger(data.candle_count) || data.candle_count < 0 || data.candle_count > data.candles.length) {
    throw new Error("The API returned an invalid completed-candle count.");
  }
  if (!data.source || !data.calculated_at || !data.latest_candle_timestamp) {
    throw new Error("The API returned incomplete analysis provenance metadata.");
  }
  if (!data.current_quote || data.current_quote.symbol !== requestedSymbol) {
    throw new Error("The API returned no current quote for the requested instrument.");
  }
  if (!Array.isArray(data.indicator_panes)) {
    throw new Error("The API returned an invalid indicator-pane contract.");
  }
  return data;
}

export default function TechnicalAnalysisPage({ user, onLogout, setPage }: { user: User; onLogout: () => void; setPage: (page: "market" | "watchlists" | "analysis") => void }) {
  const [symbol, setSymbol] = useState(SYMBOLS[0]);
  const [timeframe, setTimeframe] = useState("1h");
  const [data, setData] = useState<TechnicalAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async (force = false) => {
    const sequence = ++requestSequence.current;
    try {
      setError(null);
      setLoading(true);
      if (force) setRefreshing(true);
      setData(null);

      const response = await getTechnicalAnalysis(symbol, timeframe);
      const validated = validateAnalysisResponse(response, symbol, timeframe);
      if (sequence === requestSequence.current) setData(validated);
    } catch (err) {
      if (sequence !== requestSequence.current) return;
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setData(null);
      setError(err instanceof Error ? err.message : "Unable to retrieve technical-analysis data.");
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [onLogout, symbol, timeframe]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), ANALYSIS_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

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
  const currentQuote = data?.current_quote;
  const quotePrice = currentQuote?.price;

  return <div className="app"><header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections"><button className="nav-button" onClick={() => setPage("market")}>Market Data</button><button className="nav-button" onClick={() => setPage("watchlists")}>Watchlists</button><button className="nav-button active" onClick={() => setPage("analysis")}>Technical Analysis</button></nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={onLogout}>Sign out</button></div></header><main>
    <section className="hero"><div><div className="eyebrow">Phase 4 · Charting architecture</div><h2>Interactive financial charts backed by the verified technical-analysis API.</h2><p>The live quote is fetched separately from historical candles. Charts and deterministic indicators use completed candles only; RSI and MACD are supplied as historical indicator-pane series by the API.</p></div><div className="hero-stat"><BarChart3 size={20}/><strong>{data?.candle_count ?? 0}</strong><span>completed candles</span></div></section>
    <section className="ta-controls panel"><div><label>Instrument<select value={symbol} onChange={e => setSymbol(e.target.value)} disabled={loading || refreshing}>{SYMBOLS.map(item => <option key={item}>{item}</option>)}</select></label></div><div><label>Timeframe<select value={timeframe} onChange={e => setTimeframe(e.target.value)} disabled={loading || refreshing}>{TIMEFRAMES.map(item => <option key={item}>{item}</option>)}</select></label></div><button className="refresh" onClick={() => void load(true)} disabled={loading || refreshing}><RefreshCw size={16} className={refreshing ? "spin" : ""}/>{refreshing ? "Refreshing" : "Refresh analysis"}</button></section>
    {error && <div className="error" role="alert"><AlertTriangle size={17}/>{error}<button className="refresh" onClick={() => void load(true)} disabled={refreshing}>Retry</button></div>}
    {loading ? <div className="panel empty" role="status">Loading current quote, historical candles and indicators…</div> : !data && !error ? <div className="panel empty">No analysis is currently available.</div> : data && <><section className="ta-overview"><div className="panel"><div className="panel-head"><div><h3>{data.symbol} · {data.timeframe}</h3><span>Historical source: {data.source} · latest completed candle {formatTimestamp(data.latest_candle_timestamp)}</span></div><ShieldCheck size={20}/></div><div className="ta-price">{quotePrice?.toLocaleString(undefined, { maximumFractionDigits: 8 }) ?? "—"}</div><div className="panel-head"><span>Current quote · {currentQuote?.status ?? "UNKNOWN"} · {currentQuote?.source ?? "unknown"}</span><span>Observed: {formatTimestamp(currentQuote?.timestamp ?? undefined)}</span></div><div className={`large-status ${indicatorClass(trend)}`}><span className="dot"/>{trend}</div><div className="panel-head"><span>Last completed close: {lastCompleted?.close.toLocaleString(undefined, { maximumFractionDigits: 8 }) ?? "—"}</span><span>Calculated: {formatTimestamp(data.calculated_at)}</span></div></div><div className="panel"><div className="panel-head"><div><h3>Momentum & strength</h3><span>Calculated from the same completed candle series</span></div><Activity size={20}/></div><div className="metric-grid"><div><span>RSI (14)</span><strong>{value(data, "rsi14", 2)}</strong></div><div><span>ADX (14)</span><strong>{value(data, "adx14", 2)}</strong></div><div><span>MACD</span><strong>{value(data, "macd", 5)}</strong></div><div><span>ATR (14)</span><strong>{value(data, "atr14", 5)}</strong></div></div></div></section><section className="panel chart-panel"><div className="panel-head"><div><h3>Market chart</h3><span>Live quote is separate from the last completed candle. Chart controls provide volume, overlays, RSI, MACD, crosshair, zoom, pan and reset.</span></div></div><TechnicalChart data={data}/></section><section className="panel"><div className="panel-head"><div><h3>Indicator matrix</h3><span>Unavailable values are intentionally shown as — when history is insufficient.</span></div></div><div className="indicator-table">{rows.map(([name, result]) => <div className="indicator-row" key={name}><span>{name}</span><strong>{result}</strong></div>)}</div></section><section className="panel"><div className="panel-head"><div><h3>Recent candles</h3><span>Provider-sourced OHLCV observations · forming candles are excluded from chart and indicator calculations.</span></div></div><div className="candle-table"><div className="candle-head"><span>Timestamp</span><span>Open</span><span>High</span><span>Low</span><span>Close</span><span>Volume</span></div>{data.candles.slice(-12).reverse().map(c => <div className="candle-row" key={c.timestamp}><span>{c.timestamp}{c.is_complete ? "" : " · forming"}</span><span>{c.open}</span><span>{c.high}</span><span>{c.low}</span><span>{c.close}</span><span>{c.volume ?? "—"}</span></div>)}</div></section></>}
    <footer>Technical analysis is informational research output. It is not financial advice or a trading recommendation.</footer>
  </main></div>;
}
