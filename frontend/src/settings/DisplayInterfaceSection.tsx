import { Accessibility, BarChart3, Monitor } from "lucide-react";
import type { PreferencesDraft } from "../settingsApi";
import { SelectField, SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props {
  settings: PreferencesDraft;
  update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void;
}

const landingPages = [
  ["/dashboard", "Dashboard"],
  ["/markets/watchlists", "Watchlists"],
  ["/analysis/technical", "Technical Analysis"],
  ["/analysis/signals", "Signals"],
  ["/research/ai", "AI Market Research"],
  ["/research/reports", "Research Reports"],
] as const;

export default function DisplayInterfaceSection({ settings, update }: Props) {
  const display = settings.display_preferences;
  const patch = (value: Partial<typeof display>) => update("display_preferences", value);

  return <SettingsSection title="Display & Interface" description="Lightweight presentation preferences. These settings change how information is rendered, not the underlying research or risk algorithms." icon={Monitor}>
    <div className="settings-subheading">Appearance</div>
    <div className="settings-control-grid">
      <SettingField label="Theme"><SelectField value={display.theme} onChange={value => patch({ theme: value as typeof display.theme })} options={["system", "light", "dark"]} /></SettingField>
      <SettingField label="Density"><SelectField value={display.density} onChange={value => patch({ density: value as typeof display.density })} options={["comfortable", "compact"]} /></SettingField>
      <SettingField label="Sidebar"><SelectField value={display.sidebar_collapsed ? "collapsed" : "expanded"} onChange={value => patch({ sidebar_collapsed: value === "collapsed" })} options={["expanded", "collapsed"]} /></SettingField>
    </div>

    <div className="settings-subheading">Landing Page</div>
    <SettingField label="Default landing page" description="Applied when opening the workspace after authentication."><select className="settings-select" value={display.default_landing_page} onChange={event => patch({ default_landing_page: event.target.value as typeof display.default_landing_page })}>{landingPages.map(([path, label]) => <option key={path} value={path}>{label}</option>)}</select></SettingField>

    <div className="settings-subheading">Number Formatting</div>
    <div className="settings-control-grid">
      <SettingField label="Currency"><SelectField value={display.currency} onChange={value => patch({ currency: value as typeof display.currency })} options={["USD"]} /></SettingField>
      <SettingField label="Decimal precision"><SelectField value={display.decimal_precision} onChange={value => patch({ decimal_precision: value as typeof display.decimal_precision })} options={["auto", "0", "2", "4", "6"]} /></SettingField>
      <SettingField label="Percentage format"><SelectField value={display.percentage_format} onChange={value => patch({ percentage_format: value as typeof display.percentage_format })} options={["1.25%", "1.3%", "1%"]} /></SettingField>
      <SettingField label="Large numbers"><SelectField value={display.large_number_format} onChange={value => patch({ large_number_format: value as typeof display.large_number_format })} options={["compact", "full"]} /></SettingField>
    </div>

    <div className="settings-subheading">Time</div>
    <div className="settings-control-grid">
      <SettingField label="Timezone" description="Used when rendering interface and research timestamps."><input className="settings-input" value={display.timezone} onChange={event => patch({ timezone: event.target.value })} /></SettingField>
      <SettingField label="Market timestamps"><SelectField value={display.market_timestamps} onChange={value => patch({ market_timestamps: value as typeof display.market_timestamps })} options={["local", "utc", "exchange"]} /></SettingField>
      <SettingField label="Date format"><SelectField value={display.date_format} onChange={value => patch({ date_format: value as typeof display.date_format })} options={["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]} /></SettingField>
      <SettingField label="Time format"><SelectField value={display.time_format} onChange={value => patch({ time_format: value as typeof display.time_format })} options={["24-hour", "12-hour"]} /></SettingField>
    </div>

    <div className="settings-subheading">Charts</div>
    <div className="settings-control-grid">
      <SettingField label="Default chart type"><SelectField value={display.chart_type} onChange={value => patch({ chart_type: value as typeof display.chart_type })} options={["candlestick", "line", "area"]} /></SettingField>
      <SettingField label="Auto-refresh"><Toggle checked={display.auto_refresh} onChange={value => patch({ auto_refresh: value })} label={display.auto_refresh ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Show volume"><Toggle checked={display.show_volume} onChange={value => patch({ show_volume: value })} label={display.show_volume ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Show indicators"><Toggle checked={display.show_indicators} onChange={value => patch({ show_indicators: value })} label={display.show_indicators ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Show grid"><Toggle checked={display.show_grid} onChange={value => patch({ show_grid: value })} label={display.show_grid ? "ON" : "OFF"} /></SettingField>
      <SettingField label="Remember zoom"><Toggle checked={display.remember_zoom} onChange={value => patch({ remember_zoom: value })} label={display.remember_zoom ? "ON" : "OFF"} /></SettingField>
    </div>

    <div className="settings-subheading">Accessibility</div>
    <div className="settings-toggle-grid">
      <Toggle checked={display.reduce_animations} onChange={value => patch({ reduce_animations: value })} label="Reduce animations" />
      <Toggle checked={display.reduced_motion} onChange={value => patch({ reduced_motion: value })} label="Reduced motion" />
      <Toggle checked={display.accessible_contrast} onChange={value => patch({ accessible_contrast: value })} label="Accessible contrast" />
    </div>
    <div className="settings-health-panel"><Accessibility size={16} /><p>Keyboard-friendly controls use native buttons, inputs and selects. Reduced-motion preferences are applied through the workspace accessibility layer.</p></div>
    <div className="settings-info-note"><strong>Landing-page options</strong><span>{landingPages.map(([path, label]) => `${label} (${path})`).join(" · ")}</span></div>
    <div className="settings-info-note"><BarChart3 size={15} /><span>Chart preferences are presentation defaults. They do not alter server-side indicators, calculations or market-data validation.</span></div>
  </SettingsSection>;
}
