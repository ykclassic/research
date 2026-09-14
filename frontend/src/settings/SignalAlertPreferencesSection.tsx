import { Bell, SlidersHorizontal } from "lucide-react";
import type { PreferencesDraft } from "../settingsApi";
import { SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props {
  settings: PreferencesDraft;
  update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void;
}

const SIGNAL_TYPES = [
  ["BUY", "Long"],
  ["SELL", "Short"],
  ["NEUTRAL", "Neutral / watch"],
] as const;

const FREQUENCIES = ["Immediate", "Batched", "Daily digest", "Off"] as const;

export default function SignalAlertPreferencesSection({ settings, update }: Props) {
  const signal = settings.signal_preferences;
  const alerts = settings.alert_preferences;

  const toggleSignal = (type: "BUY" | "SELL" | "NEUTRAL") => {
    const next = signal.preferred_signal_types.includes(type)
      ? signal.preferred_signal_types.filter(value => value !== type)
      : [...signal.preferred_signal_types, type];
    if (next.length > 0) update("signal_preferences", { preferred_signal_types: next });
  };

  return <>
    <SettingsSection title="Signal Preferences" description="Settings qualify signals through the server-side signal engine. They do not duplicate signal logic in the frontend." icon={SlidersHorizontal}>
      <div className="settings-prominent-control">
        <SettingField
          label="Minimum Signal Confidence"
          description="Only signals meeting or exceeding this threshold are qualifying signals."
        >
          <div className="settings-range settings-confidence-range">
            <span>50%</span>
            <input
              aria-label="Minimum Signal Confidence"
              type="range"
              min="0.5"
              max="1"
              step="0.01"
              value={signal.minimum_confidence}
              onChange={event => update("signal_preferences", { minimum_confidence: Number(event.target.value) })}
            />
            <strong>{Math.round(signal.minimum_confidence * 100)}%</strong>
            <span>100%</span>
          </div>
        </SettingField>
      </div>

      <SettingField label="Preferred signal types" description="Select the directions that the signal engine may qualify for you.">
        <div className="settings-chip-group">
          {SIGNAL_TYPES.map(([type, label]) => (
            <button
              key={type}
              type="button"
              className={`settings-chip ${signal.preferred_signal_types.includes(type) ? "active" : ""}`}
              aria-pressed={signal.preferred_signal_types.includes(type)}
              onClick={() => toggleSignal(type)}
            >
              {label}
            </button>
          ))}
        </div>
      </SettingField>

      <SettingField label="Minimum risk/reward ratio" description="Directional signals must have at least this estimated structural risk/reward before qualifying.">
        <input
          className="settings-number-input"
          aria-label="Minimum risk/reward ratio"
          type="number"
          min="0.1"
          max="20"
          step="0.1"
          value={signal.minimum_risk_reward}
          onChange={event => update("signal_preferences", { minimum_risk_reward: Number(event.target.value) })}
        />
      </SettingField>

      <SettingField label="Require multi-timeframe confirmation" description="Require directional agreement across the existing MTF analysis before a directional signal qualifies.">
        <Toggle checked={signal.require_multi_timeframe_confirmation} onChange={value => update("signal_preferences", { require_multi_timeframe_confirmation: value })} label={signal.require_multi_timeframe_confirmation ? "Required" : "Optional"} />
      </SettingField>

      <SettingField label="Require market-structure confirmation" description="Require the existing structure analysis to confirm the signal direction.">
        <Toggle checked={signal.require_market_structure_confirmation} onChange={value => update("signal_preferences", { require_market_structure_confirmation: value })} label={signal.require_market_structure_confirmation ? "Required" : "Optional"} />
      </SettingField>
    </SettingsSection>

    <SettingsSection title="Alert Preferences" description="Global notification behavior. Individual alert rules remain managed by Alerts & Monitoring." icon={Bell}>
      <SettingField label="Notification channels" description="These are global delivery preferences; individual alert rules remain responsible for their own conditions.">
        <div className="settings-toggle-grid">
          <Toggle checked={alerts.browser_notifications_enabled} onChange={value => update("alert_preferences", { browser_notifications_enabled: value })} label="Browser notifications" />
          <Toggle checked={alerts.email_alerts_enabled} onChange={value => update("alert_preferences", { email_alerts_enabled: value })} label="Email alerts" />
          <Toggle checked={alerts.discord_alerts_enabled} onChange={value => update("alert_preferences", { discord_alerts_enabled: value })} label="Discord alerts" />
          <Toggle checked={alerts.telegram_alerts_enabled} onChange={value => update("alert_preferences", { telegram_alerts_enabled: value })} label="Telegram alerts" />
        </div>
      </SettingField>

      <SettingField label="Alert categories" description="Choose which global event categories are eligible for notification delivery.">
        <div className="settings-toggle-grid">
          <Toggle checked={alerts.high_confidence_signal_alerts} onChange={value => update("alert_preferences", { high_confidence_signal_alerts: value })} label="High-confidence signals" />
          <Toggle checked={alerts.price_alerts} onChange={value => update("alert_preferences", { price_alerts: value })} label="Price alerts" />
          <Toggle checked={alerts.regime_change_alerts} onChange={value => update("alert_preferences", { regime_change_alerts: value })} label="Regime changes" />
          <Toggle checked={alerts.news_event_alerts} onChange={value => update("alert_preferences", { news_event_alerts: value })} label="News / events" />
          <Toggle checked={alerts.report_completion_alerts} onChange={value => update("alert_preferences", { report_completion_alerts: value })} label="Research report completion" />
        </div>
      </SettingField>

      <SettingField label="Alert frequency" description="Immediate is delivered as events occur; Batched and Daily digest preserve the preference for the corresponding notification scheduler.">
        <div className="settings-chip-group" role="radiogroup" aria-label="Alert frequency">
          {FREQUENCIES.map(value => (
            <button key={value} type="button" className={`settings-chip ${alerts.frequency === value ? "active" : ""}`} aria-pressed={alerts.frequency === value} onClick={() => update("alert_preferences", { frequency: value })}>{value}</button>
          ))}
        </div>
      </SettingField>
    </SettingsSection>
  </>;
}
