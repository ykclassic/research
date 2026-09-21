import { Clock3, Gauge2, Radio } from "lucide-react";
import type { MarketSession, MarketSessionState } from "./api";

type Props = { session: MarketSession | null };

const ASSET_LABELS: Record<string, string> = {
  crypto: "Crypto",
  forex: "Forex",
  stocks: "US Equities",
};

function volatilityClass(state: MarketSessionState["volatility_state"]): string {
  return state.toLowerCase().replace("_", "-");
}

function volatilityLabel(state: MarketSessionState["volatility_state"]): string {
  return {
    VERY_HIGH: "Very High",
    HIGH: "High",
    MODERATE: "Moderate",
    LOW: "Low",
    VERY_LOW: "Very Low",
    UNKNOWN: "Unavailable",
  }[state];
}

function SessionRow({ state }: { state: MarketSessionState }) {
  const open = state.status === "OPEN";
  const volatility = volatilityClass(state.volatility_state);
  return (
    <article className={`trading-session-row ${volatility} ${open ? "is-open" : "is-closed"}`}>
      <div className="trading-session-main">
        <span className={`trading-session-indicator ${open ? "pulse" : ""}`} aria-hidden="true" />
        <div>
          <div className="trading-session-asset">{ASSET_LABELS[state.asset_class] ?? state.asset_class}</div>
          <strong>{state.label}</strong>
        </div>
      </div>
      <div className="trading-session-metrics">
        <div>
          <span>Volatility</span>
          <strong>{state.volatility_score == null ? "—" : `${state.volatility_score.toFixed(0)} / 100`}</strong>
        </div>
        <div>
          <span>State</span>
          <strong>{volatilityLabel(state.volatility_state)}</strong>
        </div>
        <div>
          <span>Liquidity</span>
          <strong>{state.liquidity_state.replace("_", " ")}</strong>
        </div>
      </div>
      <div className="trading-session-transition">
        <Clock3 size={14} />
        <span>{state.asset_class === "crypto" ? "24/7 market" : open ? `Status: Open` : "Market closed"}</span>
      </div>
    </article>
  );
}

export default function TradingSessionPanel({ session }: Props) {
  return (
    <section className="panel trading-session-panel" aria-label="Trading session and market volatility">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Live market activity</div>
          <h3>Trading Session</h3>
          <span>Session timing is asset-class aware. Color and pulse intensity follow normalized recent volatility.</span>
        </div>
        <div className="trading-session-legend" aria-label="Volatility legend">
          <span className="legend-dot very-low" /> Low
          <span className="legend-dot moderate" /> Moderate
          <span className="legend-dot high" /> High
        </div>
      </div>
      {!session ? (
        <div className="trading-session-loading"><Radio size={16} /> Calculating current market activity…</div>
      ) : (
        <div className="trading-session-grid">
          {session.sessions.map(state => <SessionRow key={state.asset_class} state={state} />)}
        </div>
      )}
      <div className="trading-session-footnote">
        <Gauge2 size={14} />
        <span>Volatility is normalized against recent completed hourly candles for a liquid representative asset in each market class.</span>
      </div>
    </section>
  );
}
