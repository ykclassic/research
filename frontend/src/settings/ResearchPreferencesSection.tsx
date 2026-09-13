import type { PreferencesDraft } from "../settingsApi";
import { SelectField, SettingField, SettingsSection, Toggle } from "./SettingsSection";
import { FlaskConical } from "lucide-react";

interface Props { settings: PreferencesDraft; update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void; }

export default function ResearchPreferencesSection({ settings, update }: Props) {
  const research = settings.research_preferences;
  return <SettingsSection title="Research Preferences" description="Define the default workflow the research engine uses when you start an analysis." icon={FlaskConical}>
    <div className="settings-subheading">Default research settings</div>
    <div className="settings-control-grid">
      <SettingField label="Default asset" description="Used when a research workflow does not specify an asset."><input className="settings-input" value={research.default_asset} onChange={event => update("research_preferences", { default_asset: event.target.value })} /></SettingField>
      <SettingField label="Default asset class"><SelectField value={research.default_asset_class} onChange={value => update("research_preferences", { default_asset_class: value as typeof research.default_asset_class })} options={["Crypto", "Forex", "Stocks"]} /></SettingField>
      <SettingField label="Default timeframe"><SelectField value={research.default_timeframe} onChange={value => update("research_preferences", { default_timeframe: value as typeof research.default_timeframe })} options={["15m", "1h", "4h", "1D"]} /></SettingField>
      <SettingField label="Default analysis depth" description="Controls how much analysis the default research workflow requests."><SelectField value={research.analysis_depth} onChange={value => update("research_preferences", { analysis_depth: value as typeof research.analysis_depth })} options={["Quick", "Standard", "Comprehensive"]} /></SettingField>
    </div>
    <div className="settings-subheading">Analysis preferences</div>
    <div className="settings-toggle-grid">
      <Toggle checked={research.technical_analysis_enabled} onChange={value => update("research_preferences", { technical_analysis_enabled: value })} label="Technical analysis" />
      <Toggle checked={research.market_structure_enabled} onChange={value => update("research_preferences", { market_structure_enabled: value })} label="Market structure" />
      <Toggle checked={research.multi_timeframe_enabled} onChange={value => update("research_preferences", { multi_timeframe_enabled: value })} label="Multi-timeframe analysis" />
      <Toggle checked={research.fundamental_analysis_enabled} onChange={value => update("research_preferences", { fundamental_analysis_enabled: value })} label="Fundamental analysis" />
      <Toggle checked={research.news_analysis_enabled} onChange={value => update("research_preferences", { news_analysis_enabled: value })} label="News analysis" />
      <Toggle checked={research.ai_interpretation_enabled} onChange={value => update("research_preferences", { ai_interpretation_enabled: value })} label="AI interpretation" />
    </div>
  </SettingsSection>;
}
