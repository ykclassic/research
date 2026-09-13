import { DatabaseBackup, LockKeyhole } from "lucide-react";
import type { PreferencesDraft } from "../settingsApi";
import { SelectField, SettingField, SettingsSection, Toggle } from "./SettingsSection";

interface Props { settings: PreferencesDraft; update: <K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => void; }

export default function PrivacyDataSystemSection({ settings, update }: Props) {
  const privacy = settings.privacy_preferences;
  return <SettingsSection title="Privacy, Data & System" description="Control persistence choices and expose the system state relevant to your research workspace." icon={LockKeyhole}>
    <div className="settings-control-grid">
      <SettingField label="Research history retention" description="How long newly generated history should be retained by retention-aware services."><SelectField value={String(privacy.research_history_retention_days)} onChange={value => update("privacy_preferences", { research_history_retention_days: Number(value) })} options={["30", "90", "365", "730", "3650", "0"]} /></SettingField>
    </div>
    <div className="settings-toggle-grid">
      <Toggle checked={privacy.save_generated_reports} onChange={value => update("privacy_preferences", { save_generated_reports: value })} label="Save generated reports" />
      <Toggle checked={privacy.save_ai_research} onChange={value => update("privacy_preferences", { save_ai_research: value })} label="Save AI research" />
      <Toggle checked={privacy.save_search_history} onChange={value => update("privacy_preferences", { save_search_history: value })} label="Save search history" />
      <Toggle checked={privacy.analytics_telemetry_enabled} onChange={value => update("privacy_preferences", { analytics_telemetry_enabled: value })} label="Analytics / telemetry" />
    </div>
    <div className="settings-data-actions">
      <div className="settings-data-action"><DatabaseBackup size={17} /><div><strong>Data management</strong><span>Export and deletion workflows will be expanded in the Privacy & Data phase. Destructive history and watchlist deletion is already available in Account & Security.</span></div></div>
      <div className="settings-system-grid">
        <div><span>Application</span><strong>Adaptive Market Research</strong></div>
        <div><span>Authentication</span><strong className="settings-status-ok">● Authenticated</strong></div>
        <div><span>Preferences</span><strong>Persistent · RLS protected</strong></div>
        <div><span>Provider secrets</span><strong>Server-side only</strong></div>
      </div>
    </div>
  </SettingsSection>;
}
