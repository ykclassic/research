import { Activity, ShieldCheck } from "lucide-react";
import { MarketRegime, RegimeResult } from "./api";
import "./regime-panel.css";

const REGIME_LABELS: Record<MarketRegime, string> = {
  STRONG_TREND_UP: "Strong Trend Up", STRONG_TREND_DOWN: "Strong Trend Down", WEAK_TREND: "Weak Trend",
  RANGE: "Range", HIGH_VOLATILITY: "High Volatility", LOW_VOLATILITY: "Low Volatility", UNKNOWN: "Unknown",
};
function formatNumber(value: number | null | undefined, digits = 3): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
}
function formatTimestamp(timestamp: string | null | undefined): string {
  if (!timestamp) return "—";
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString(undefined, { timeZone: "UTC", hour12: false }) + " UTC";
}
function regimeClass(regime: MarketRegime): string { return `regime-${regime.toLowerCase().replaceAll("_", "-")}`; }

export function validateRegimeResponse(data: RegimeResult, requestedSymbol: string, requestedTimeframe: string): RegimeResult {
  if (data.symbol !== requestedSymbol) throw new Error(`The regime API returned ${data.symbol} instead of ${requestedSymbol}.`);
  if (data.timeframe !== requestedTimeframe) throw new Error(`The regime API returned timeframe ${data.timeframe} instead of ${requestedTimeframe}.`);
  if (!data.source || !data.calculated_at || !data.latest_candle_timestamp || !data.provider_timestamp) throw new Error("The regime API returned incomplete provenance metadata.");
  if (!Number.isInteger(data.candle_count) || data.candle_count < 1) throw new Error("The regime API returned an invalid candle count.");
  if (!Number.isFinite(data.confidence) || data.confidence < 0 || data.confidence > 1) throw new Error("The regime API returned confidence outside the [0, 1] contract.");
  if (!data.evidence || !data.thresholds || !data.rule_id || !data.rule) throw new Error("The regime API returned incomplete regime evidence.");
  return data;
}

export default function RegimePanel({ data, loading, error, onRetry }: { data: RegimeResult | null; loading: boolean; error: string | null; onRetry: () => void; }) {
  if (loading) return <section className="panel regime-panel" aria-label="Market regime" aria-busy="true"><div className="regime-loading"><Activity size={18} className="spin"/><span>Loading deterministic market-regime evidence…</span></div></section>;
  if (!data) return <section className="panel regime-panel" aria-label="Market regime"><div className="regime-panel-head"><div><h3>Market regime</h3><span>Deterministic regime research is unavailable.</span></div></div>{error && <div className="regime-error" role="alert"><span>{error}</span><button className="refresh" onClick={onRetry}>Retry</button></div>}</section>;

  const e = data.evidence; const t = data.thresholds; const confidencePercent = Math.round(data.confidence * 100);
  const metrics: Array<[string, string]> = [
    ["ADX (14)", formatNumber(e.adx, 2)], ["ATR %", formatNumber(e.atr_percent, 4)], ["ATR percentile", formatNumber(e.atr_percentile, 3)],
    ["BB width", formatNumber(e.bb_width, 5)], ["BB width percentile", formatNumber(e.bb_width_percentile, 3)],
    ["Trend persistence", formatNumber(e.trend_persistence, 3)], ["Directional move ratio", formatNumber(e.directional_move_ratio, 3)], ["Trend direction", e.trend_direction || "—"],
  ];
  const degraded = data.fallback_used || data.freshness_status === "STALE" || data.cache_hit;

  return (
    <section className="panel regime-panel" aria-label="Market regime">
      <div className="regime-panel-head">
        <div><div className="eyebrow">Phase 5.4 · Regime research</div><h3>Market regime</h3><span>Deterministic classification from completed provider candles. No AI or frontend-derived classification.</span></div><ShieldCheck size={20}/>
      </div>
      {degraded && <div className="regime-error" role="status"><span>Degraded data path: {data.fallback_used ? "provider fallback" : data.cache_hit ? "canonical cache" : data.freshness_status?.toLowerCase()}. Research freshness is shown explicitly below.</span></div>}
      <div className="regime-summary">
        <div className={`regime-badge ${regimeClass(data.regime)}`}><span className="regime-dot"/><strong>{REGIME_LABELS[data.regime]}</strong><span>{data.rule_id}</span></div>
        <div className="regime-confidence"><div className="regime-confidence-head"><span>Confidence</span><strong>{confidencePercent}%</strong></div><div className="regime-confidence-track"><span style={{ width: `${confidencePercent}%` }}/></div></div>
      </div>
      <div className="regime-metrics">{metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <div className="regime-evidence">
        <div><span>Price</span><strong>{formatNumber(e.price, 8)}</strong></div><div><span>EMA 50</span><strong>{formatNumber(e.ema_50, 8)}</strong></div><div><span>EMA 200</span><strong>{formatNumber(e.ema_200, 8)}</strong></div>
        <div><span>Price &gt; EMA 200</span><strong>{e.price_above_ema_200 == null ? "—" : e.price_above_ema_200 ? "Yes" : "No"}</strong></div>
        <div><span>EMA 50 &gt; EMA 200</span><strong>{e.ema_50_above_ema_200 == null ? "—" : e.ema_50_above_ema_200 ? "Yes" : "No"}</strong></div>
      </div>
      <div className="regime-rule"><span>Classification rule · {data.rule_id}</span><strong>{data.rule}</strong></div>
      <details className="regime-thresholds"><summary>Show canonical thresholds</summary><div className="threshold-grid">
        <div><span>ADX strong</span><strong>{t.adx_strong}</strong></div><div><span>Persistence strong</span><strong>{t.persistence_strong}</strong></div><div><span>Persistence weak</span><strong>{t.persistence_weak}</strong></div>
        <div><span>Directional ratio strong</span><strong>{t.directional_ratio_strong}</strong></div><div><span>Directional ratio weak</span><strong>{t.directional_ratio_weak}</strong></div>
        <div><span>Volatility high percentile</span><strong>{t.volatility_high_percentile}</strong></div><div><span>Volatility low percentile</span><strong>{t.volatility_low_percentile}</strong></div>
      </div></details>
      <div className="regime-provenance">
        <span>Source: <strong>{data.source}</strong></span><span>Provider timestamp: <strong>{formatTimestamp(data.provider_timestamp)}</strong></span>
        <span>Latest completed candle: <strong>{formatTimestamp(data.latest_candle_timestamp)}</strong></span><span>Calculated: <strong>{formatTimestamp(data.calculated_at)}</strong></span>
        <span>Freshness: <strong>{data.freshness_status ?? "UNKNOWN"}</strong></span><span>Data age: <strong>{formatNumber(data.freshness_age_seconds, 1)}s</strong></span>
        <span>Request latency: <strong>{data.request_latency_ms ?? "—"}ms</strong></span><span>Provider attempts: <strong>{data.provider_attempts?.join(" → ") || data.source}</strong></span>
        <span>Candles: <strong>{data.candle_count}</strong></span>
      </div>
    </section>
  );
}
