import { BrainCircuit } from "lucide-react";
import type { PreferencesDraft } from "../settingsApi";
import { SelectField, SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props { settings: PreferencesDraft; update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void; }

const OUTPUTS: Array<[keyof PreferencesDraft["ai_preferences"]["output_sections"], string]> = [
  ["executive_summary", "Executive summary"], ["technical_outlook", "Technical outlook"], ["fundamental_outlook", "Fundamental outlook"], ["news_impact", "News impact"], ["market_regime", "Market regime"], ["bull_scenario", "Bull scenario"], ["base_scenario", "Base scenario"], ["bear_scenario", "Bear scenario"], ["key_risks", "Key risks"], ["catalysts", "Catalysts"], ["invalidations", "Invalidations"],
];

export default function AIResearchSection({ settings, update }: Props) {
  const ai = settings.ai_preferences;
  return <SettingsSection title="AI & Research Intelligence" description="Configure AI interpretation and output presentation. Core analytical safeguards remain server-controlled." icon={BrainCircuit}>
    <div className="settings-toggle-grid">
      <Toggle checked={ai.enabled} onChange={value => update("ai_preferences", { enabled: value })} label="AI research enabled" />
      <Toggle checked={ai.require_evidence} onChange={value => update("ai_preferences", { require_evidence: value })} label="Require evidence before conclusion" />
      <Toggle checked={ai.show_confidence_scores} onChange={value => update("ai_preferences", { show_confidence_scores: value })} label="Show confidence scores" />
      <Toggle checked={ai.show_supporting_indicators} onChange={value => update("ai_preferences", { show_supporting_indicators: value })} label="Show supporting indicators" />
      <Toggle checked={ai.show_conflicting_evidence} onChange={value => update("ai_preferences", { show_conflicting_evidence: value })} label="Show conflicting evidence" />
    </div>
    <div className="settings-control-grid">
      <SettingField label="Preferred analysis style"><SelectField value={ai.analysis_style} onChange={value => update("ai_preferences", { analysis_style: value as typeof ai.analysis_style })} options={["Concise", "Analytical", "Detailed"]} /></SettingField>
      <SettingField label="Interpretation risk profile"><SelectField value={ai.interpretation_risk} onChange={value => update("ai_preferences", { interpretation_risk: value as typeof ai.interpretation_risk })} options={["Conservative", "Balanced", "Aggressive"]} /></SettingField>
    </div>
    <div className="settings-subheading">Research output</div>
    <div className="settings-toggle-grid">{OUTPUTS.map(([key, label]) => <Toggle key={key} checked={ai.output_sections[key]} onChange={value => update("ai_preferences", { output_sections: { ...ai.output_sections, [key]: value } })} label={label} />)}</div>
    <div className="settings-health-panel"><p>These settings affect presentation and user preference. They cannot disable data validation, alter provider provenance, bypass deterministic gates, or modify core risk controls.</p></div>
  </SettingsSection>;
}
