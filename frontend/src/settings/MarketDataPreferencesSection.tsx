import { Database, ShieldCheck } from "lucide-react";
import type { PreferencesDraft } from "../settingsApi";
import { SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props { settings: PreferencesDraft; update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void; }

export default function MarketDataPreferencesSection({ settings, update }: Props) {
  const data = settings.market_data_preferences;
  return <SettingsSection title="Market Data Preferences" description="Control freshness and candle-quality rules used when research consumes market data." icon={Database}>
    <div className="settings-control-grid">
      <SettingField label="Maximum acceptable data age" description="Research should reject data older than this threshold when stale-data rejection is enabled."><div className="settings-unit-input"><input className="settings-number-input" type="number" min="5" max="86400" value={data.maximum_data_age_seconds} onChange={event => update("market_data_preferences", { maximum_data_age_seconds: Number(event.target.value) })} /><span>seconds</span></div></SettingField>
      <SettingField label="Reject stale data"><Toggle checked={data.reject_stale_data} onChange={value => update("market_data_preferences", { reject_stale_data: value })} label={data.reject_stale_data ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Require completed candles"><Toggle checked={data.require_completed_candles} onChange={value => update("market_data_preferences", { require_completed_candles: value })} label={data.require_completed_candles ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Allow validated cache fallback" description="Only validated canonical cache entries should qualify as fallback data."><Toggle checked={data.allow_cached_data_fallback} onChange={value => update("market_data_preferences", { allow_cached_data_fallback: value })} label={data.allow_cached_data_fallback ? "ON" : "OFF"} /></SettingField>
    </div>
    <div className="settings-health-panel"><div className="settings-health-title"><ShieldCheck size={16} /><strong>Data integrity policy</strong></div><p>Provider credentials and secrets remain server-side. This section controls user-level freshness behavior; it does not override provider validation, provenance checks or canonical-cache integrity rules.</p></div>
  </SettingsSection>;
}
