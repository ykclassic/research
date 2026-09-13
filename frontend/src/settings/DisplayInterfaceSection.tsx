import { Monitor } from "lucide-react";
import type { PreferencesDraft } from "../settingsApi";
import { SelectField, SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props { settings: PreferencesDraft; update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void; }

export default function DisplayInterfaceSection({ settings, update }: Props) {
  const display = settings.display_preferences;
  return <SettingsSection title="Display & Interface" description="Personalize how the research workspace is presented without changing analytical behavior." icon={Monitor}>
    <div className="settings-control-grid">
      <SettingField label="Theme"><SelectField value={display.theme} onChange={value => update("display_preferences", { theme: value as typeof display.theme })} options={["system", "dark", "light"]} /></SettingField>
      <SettingField label="Density"><SelectField value={display.density} onChange={value => update("display_preferences", { density: value as typeof display.density })} options={["comfortable", "compact"]} /></SettingField>
      <SettingField label="Default landing page"><SelectField value={display.default_landing_page} onChange={value => update("display_preferences", { default_landing_page: value })} options={["/dashboard", "/markets/watchlists", "/analysis/technical", "/analysis/signals", "/research/ai", "/research/reports"]} /></SettingField>
      <SettingField label="Currency"><SelectField value={display.currency} onChange={value => update("display_preferences", { currency: value as typeof display.currency })} options={["USD"]} /></SettingField>
      <SettingField label="Timezone" description="Used when rendering timestamps for reports, alerts and the interface."><input className="settings-input" value={display.timezone} onChange={event => update("display_preferences", { timezone: event.target.value })} /></SettingField>
      <SettingField label="Market timestamps"><SelectField value={display.market_timestamps} onChange={value => update("display_preferences", { market_timestamps: value as typeof display.market_timestamps })} options={["local", "utc", "exchange"]} /></SettingField>
      <SettingField label="Date format"><SelectField value={display.date_format} onChange={value => update("display_preferences", { date_format: value as typeof display.date_format })} options={["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]} /></SettingField>
      <SettingField label="Time format"><SelectField value={display.time_format} onChange={value => update("display_preferences", { time_format: value as typeof display.time_format })} options={["24-hour", "12-hour"]} /></SettingField>
    </div>
    <div className="settings-toggle-grid">
      <Toggle checked={display.sidebar_collapsed} onChange={value => update("display_preferences", { sidebar_collapsed: value })} label="Collapse sidebar by default" />
      <Toggle checked={display.reduce_animations} onChange={value => update("display_preferences", { reduce_animations: value })} label="Reduce animations" />
    </div>
  </SettingsSection>;
}
