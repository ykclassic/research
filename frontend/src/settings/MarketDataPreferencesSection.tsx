import { Database, RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { MarketDataHealth, MarketDataHealthProvider, PreferencesDraft } from "../settingsApi";
import { getMarketDataHealth } from "../settingsApi";
import { SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props {
  settings: PreferencesDraft;
  update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void;
}

const ROLE_LABELS: Record<MarketDataHealthProvider["role"], string> = {
  primary: "Primary Provider",
  crypto_fallback: "Crypto Fallback",
  forex: "Forex Provider",
  stocks: "Stock Provider",
};

function formatTimestamp(value: string | null): string {
  if (!value) return "Not observed";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";
  return date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function statusClass(status: MarketDataHealthProvider["status"]): string {
  return `settings-health-status settings-health-status-${status.toLowerCase()}`;
}

export default function MarketDataPreferencesSection({ settings, update }: Props) {
  const data = settings.market_data_preferences;
  const [health, setHealth] = useState<MarketDataHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  const loadHealth = useCallback(async (refresh = false) => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      setHealth(await getMarketDataHealth(refresh));
    } catch (error) {
      setHealthError(error instanceof Error ? error.message : "Unable to load market-data health.");
    } finally {
      setHealthLoading(false);
    }
  }, []);

  useEffect(() => { void loadHealth(); }, [loadHealth]);

  const providerFor = (role: MarketDataHealthProvider["role"]) => health?.providers.find(item => item.role === role);

  return <SettingsSection title="Market Data Preferences" description="Control freshness and candle-quality rules used when research consumes market data." icon={Database}>
    <div className="settings-control-grid">
      <SettingField label="Maximum acceptable data age" description="The maximum provider-data age accepted by research when stale-data rejection is enabled.">
        <select className="settings-select" value={data.maximum_data_age_seconds} onChange={event => update("market_data_preferences", { maximum_data_age_seconds: Number(event.target.value) as 30 | 60 | 300 | 900 })}>
          <option value={30}>30 seconds</option>
          <option value={60}>1 minute</option>
          <option value={300}>5 minutes</option>
          <option value={900}>15 minutes</option>
        </select>
      </SettingField>
      <SettingField label="Reject stale data" description="Block stale quotes/candles instead of allowing them into research when validation fails."><Toggle checked={data.reject_stale_data} onChange={value => update("market_data_preferences", { reject_stale_data: value })} label={data.reject_stale_data ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Require completed candles" description="Exclude currently forming candles from analytical datasets when enabled."><Toggle checked={data.require_completed_candles} onChange={value => update("market_data_preferences", { require_completed_candles: value })} label={data.require_completed_candles ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Allow validated cache fallback" description="Permit previously validated cache data when live providers cannot supply acceptable data."><Toggle checked={data.allow_cached_data_fallback} onChange={value => update("market_data_preferences", { allow_cached_data_fallback: value })} label={data.allow_cached_data_fallback ? "ON" : "OFF"} /></SettingField>
    </div>

    <div className="settings-subheading">Market Data Health</div>
    <div className="settings-market-health-panel">
      <div className="settings-market-health-header">
        <div><strong>MARKET DATA HEALTH</strong><span>Live backend/provider diagnostics. Status is learned from real provider responses.</span></div>
        <button className="settings-secondary-button" type="button" onClick={() => void loadHealth(true)} disabled={healthLoading} title="Refresh provider health"><RefreshCw size={13} className={healthLoading ? "settings-loading-icon" : ""} />Refresh</button>
      </div>

      {healthError && <div className="settings-inline-error">{healthError}</div>}
      {healthLoading && !health && <div className="settings-health-empty">Checking configured market-data providers…</div>}
      {!healthLoading && health && <>
        <div className="settings-provider-grid">
          {(["primary", "crypto_fallback", "forex", "stocks"] as const).map(role => {
            const provider = providerFor(role);
            return <div className="settings-provider-card" key={role}>
              <div className="settings-provider-card-top">
                <span>{ROLE_LABELS[role]}</span>
                {provider ? <span className={statusClass(provider.status)}><i />{provider.status}</span> : <span className="settings-health-status settings-health-status-unknown"><i />UNKNOWN</span>}
              </div>
              <strong>{provider?.provider ?? "Not reported"}</strong>
              <div className="settings-provider-meta"><span>Last successful</span><b>{formatTimestamp(provider?.last_successful_request ?? null)}</b></div>
              <div className="settings-provider-meta"><span>Validation</span><b>{provider?.validation_status ?? "NOT_CHECKED"}</b></div>
              <div className="settings-provider-meta"><span>Provenance</span><b>{provider?.provenance_available ? "Available" : "Not available"}</b></div>
              <div className="settings-provider-meta"><span>Fallback</span><b>{provider?.fallback_status ?? "NOT_CHECKED"}</b></div>
              <div className="settings-provider-meta"><span>Cache</span><b>{provider?.cache_status ?? "UNKNOWN"}</b></div>
              <small>{provider?.message ?? "No health observation available."}</small>
            </div>;
          })}
        </div>

        <div className="settings-health-summary-grid">
          <div><span>Last health check</span><strong>{formatTimestamp(health.checked_at)}</strong></div>
          <div><span>Data validation</span><strong>{health.providers.some(item => item.validation_status === "PASSED") ? "✓ Passed" : "Not confirmed"}</strong></div>
          <div><span>Candle completeness</span><strong>{health.providers.some(item => item.candle_completeness === "PASSED") ? "✓ Passed" : "Not checked"}</strong></div>
          <div><span>Provider provenance</span><strong>{health.providers.some(item => item.provenance_available) ? "✓ Available" : "Not available"}</strong></div>
        </div>
      </>}
    </div>

    <div className="settings-health-panel"><ShieldCheck size={16} /><p>Provider credentials, API keys, API secrets and server environment variables are never returned by this diagnostic API. User preferences govern acceptance behavior; provider configuration remains server-side.</p></div>
  </SettingsSection>;
}
