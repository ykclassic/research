import { Bell, SlidersHorizontal } from "lucide-react";
import type { PreferencesDraft } from "../settingsApi";
import { SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props { settings: PreferencesDraft; update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void; }

export default function SignalAlertPreferencesSection({ settings, update }: Props) {
  const signal = settings.signal_preferences;
  const alerts = settings.alert_preferences;
  const toggleSignal = (type: "BUY" | "SELL" | "NEUTRAL") => {
    const next = signal.preferred_signal_types.includes(type)
      ? signal.preferred_signal_types.filter(value => value !== type)
      : [...signal.preferred_signal_types, type];
    if (next.length) update("signal_preferences", { preferred_signal_types: next });
  };
  return <>
    <SettingsSection title="Signal Preferences" description="Control signal qualification without changing the underlying signal engine." icon={SlidersHorizontal}>
      <SettingField label="Minimum confidence threshold" description={`${Math.round(signal.minimum_confidence * 100)}% minimum confidence. This is the main control for signal noise.`}>
        <div className="settings-range"><input type="range" min="0.5" max="1" step="0.01" value={signal.minimum_confidence} onChange={event => update("signal_preferences", { minimum_confidence: Number(event.target.value) })} /><strong>{Math.round(signal.minimum_confidence * 100)}%</strong></div>
      </SettingField>
      <SettingField label="Preferred signal types" description="Choose which signal directions qualify for your workspace.">
        <div className="settings-chip-group">{(["BUY", "SELL", "NEUTRAL"] as const).map(type => <button key={type} type="button" className={`settings-chip ${signal.preferred_signal_types.includes(type) ? "active" : ""}`} onClick={() => toggleSignal(type)}>{type === "BUY" ? "Long" : type === "SELL" ? "Short" : "Neutral / watch"}</button>)}</div>
      </SettingField>
      <SettingField label="Minimum risk/reward ratio"><input className="settings-number-input" type="number" min="0.1" max="20" step="0.1" value={signal.minimum_risk_reward} onChange={event => update("signal_preferences", { minimum_risk_reward: Number(event.target.value) })} /></SettingField>
      <SettingField label="Require multi-timeframe confirmation"><Toggle checked={signal.require_multi_timeframe_confirmation} onChange={value => update("signal_preferences", { require_multi_timeframe_confirmation: value })} label={signal.require_multi_timeframe_confirmation ? "Required" : "Optional"} /></SettingField>
      <SettingField label="Require market-structure confirmation"><Toggle checked={signal.require_market_structure_confirmation} onChange={value => update("signal_preferences", { require_market_structure_confirmation: value })} label={signal.require_market_structure_confirmation ? "Required" : "Optional"} /></SettingField>
    </SettingsSection>

    <SettingsSection title="Alert Preferences" description="Set the global behavior of the existing Alerts & Monitoring area." icon={Bell}>
      <div className="settings-toggle-grid">
        <Toggle checked={alerts.browser_notifications_enabled} onChange={value => update("alert_preferences", { browser_notifications_enabled: value })} label="Browser notifications" />
        <Toggle checked={alerts.email_alerts_enabled} onChange={value => update("alert_preferences", { email_alerts_enabled: value })} label="Email alerts" />
        <Toggle checked={alerts.high_confidence_signal_alerts} onChange={value => update("alert_preferences", { high_confidence_signal_alerts: value })} label="High-confidence signals" />
        <Toggle checked={alerts.price_alerts} onChange={value => update("alert_preferences", { price_alerts: value })} label="Price alerts" />
        <Toggle checked={alerts.regime_change_alerts} onChange={value => update("alert_preferences", { regime_change_alerts: value })} label="Regime-change alerts" />
        <Toggle checked={alerts.news_event_alerts} onChange={value => update("alert_preferences", { news_event_alerts: value })} label="News / event alerts" />
        <Toggle checked={alerts.report_completion_alerts} onChange={value => update("alert_preferences", { report_completion_alerts: value })} label="Report completion" />
      </div>
      <SettingField label="Alert frequency"><div className="settings-chip-group">{(["Immediate", "Batched", "Daily digest", "Off"] as const).map(value => <button key={value} type="button" className={`settings-chip ${alerts.frequency === value ? "active" : ""}`} onClick={() => update("alert_preferences", { frequency: value })}>{value}</button>)}</div></SettingField>
    </SettingsSection>
  </>;
}
