import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Settings as SettingsIcon } from "lucide-react";
import type { User } from "./api";
import { getAccountInfo, getPreferences, resetPreferences, savePreferences, type AccountInfo, type PreferencesDraft, type UserPreferences } from "./settingsApi";
import AccountSecuritySection from "./settings/AccountSecuritySection";
import ResearchPreferencesSection from "./settings/ResearchPreferencesSection";
import SignalAlertPreferencesSection from "./settings/SignalAlertPreferencesSection";
import MarketDataPreferencesSection from "./settings/MarketDataPreferencesSection";
import DisplayInterfaceSection from "./settings/DisplayInterfaceSection";
import AIResearchSection from "./settings/AIResearchSection";
import PrivacyDataSystemSection from "./settings/PrivacyDataSystemSection";
import SettingsSaveBar from "./settings/SettingsSaveBar";

function draftFromPreferences(value: UserPreferences): PreferencesDraft {
  return {
    research_preferences: structuredClone(value.research_preferences),
    signal_preferences: structuredClone(value.signal_preferences),
    alert_preferences: structuredClone(value.alert_preferences),
    market_data_preferences: structuredClone(value.market_data_preferences),
    display_preferences: structuredClone(value.display_preferences),
    ai_preferences: structuredClone(value.ai_preferences),
    privacy_preferences: structuredClone(value.privacy_preferences),
  };
}

function serialize(value: PreferencesDraft | null): string {
  return JSON.stringify(value);
}

interface Props {
  user: User;
  onLogout: () => void;
  setPage: (page: "market" | "watchlists" | "analysis" | "market-structure" | "mtf" | "signals" | "portfolio" | "ai-research" | "news-research" | "research-reports" | "research-history" | "alerts" | "settings" | "billing") => void;
}

const NAV = [
  ["account-security", "Account & Security"],
  ["research-preferences", "Research Preferences"],
  ["signal-alerts", "Signal & Alert Preferences"],
  ["market-data", "Market Data"],
  ["display-interface", "Display & Interface"],
  ["ai-research", "AI & Research Intelligence"],
  ["privacy-data", "Privacy, Data & System"],
] as const;

export default function SettingsPage({ user, onLogout, setPage }: Props) {
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [original, setOriginal] = useState<PreferencesDraft | null>(null);
  const [draft, setDraft] = useState<PreferencesDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null); setStatus(null);
    try {
      const [accountInfo, preferences] = await Promise.all([getAccountInfo(), getPreferences()]);
      const nextDraft = draftFromPreferences(preferences);
      setAccount(accountInfo);
      setOriginal(nextDraft);
      setDraft(nextDraft);
    } catch (value) {
      if (value instanceof Error && "status" in value && (value as { status?: number }).status === 401) { onLogout(); return; }
      setError(value instanceof Error ? value.message : "Unable to load settings.");
    } finally { setLoading(false); }
  }, [onLogout]);

  useEffect(() => { void load(); }, [load]);

  const dirty = useMemo(() => serialize(draft) !== serialize(original), [draft, original]);

  const update = useCallback(<K extends keyof PreferencesDraft>(group: K, patch: Partial<PreferencesDraft[K]>) => {
    setDraft(current => {
      if (!current) return current;
      const currentGroup = current[group] as object;
      return { ...current, [group]: { ...currentGroup, ...patch } } as PreferencesDraft;
    });
    setStatus(null); setError(null);
  }, []);

  const save = async () => {
    if (!draft) return;
    setSaving(true); setError(null); setStatus(null);
    try {
      const saved = await savePreferences(draft);
      const next = draftFromPreferences(saved);
      setDraft(next); setOriginal(next); setStatus("Settings saved successfully.");
    } catch (value) {
      if (value instanceof Error && "status" in value && (value as { status?: number }).status === 401) { onLogout(); return; }
      setError(value instanceof Error ? value.message : "Unable to save settings.");
    } finally { setSaving(false); }
  };

  const resetDraft = () => {
    if (!original) return;
    setDraft(structuredClone(original)); setError(null); setStatus("Unsaved changes discarded.");
  };

  const resetDefaults = async () => {
    if (!window.confirm("Reset all saved preferences to the application defaults?")) return;
    setResetting(true); setError(null); setStatus(null);
    try {
      const saved = await resetPreferences();
      const next = draftFromPreferences(saved);
      setDraft(next); setOriginal(next); setStatus("Settings reset to defaults.");
    } catch (value) {
      if (value instanceof Error && "status" in value && (value as { status?: number }).status === 401) { onLogout(); return; }
      setError(value instanceof Error ? value.message : "Unable to reset settings.");
    } finally { setResetting(false); }
  };

  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  if (loading) return <div className="app settings-app"><main className="settings-page"><div className="settings-loading"><SettingsIcon size={22} className="settings-loading-icon" /><strong>Loading your settings…</strong><span>Fetching account and preference state.</span></div></main></div>;
  if (!draft || !account) return <div className="app settings-app"><main className="settings-page"><div className="settings-error-state"><AlertTriangle size={22} /><strong>Settings could not be loaded.</strong><span>{error ?? "The settings service did not return a valid response."}</span><button className="settings-primary-button" onClick={() => void load()}>Retry</button></div></main></div>;

  return <div className="app settings-app">
    <main className="settings-page">
      <section className="settings-hero">
        <div><div className="eyebrow">System · Settings</div><h2>Research workspace settings.</h2><p>Configure your account, research workflow, signals, market-data behavior, AI presentation and privacy preferences from one user-scoped control center.</p></div>
        <div className="settings-hero-badge"><CheckCircle2 size={18} /><span>Authenticated workspace</span><strong>{user.email}</strong></div>
      </section>

      <div className="settings-layout">
        <aside className="settings-nav" aria-label="Settings sections">
          <div className="settings-nav-title">Settings</div>
          <button type="button" className="settings-nav-item settings-nav-billing" onClick={() => setPage("billing")}><span>08</span>Plans & Billing</button>
          {NAV.map(([id, label], index) => <button key={id} type="button" className="settings-nav-item" onClick={() => jump(id)}><span>{String(index + 1).padStart(2, "0")}</span>{label}</button>)}
        </aside>

        <div className="settings-content">
          <div id="account-security"><AccountSecuritySection account={account} onLogout={onLogout} /></div>
          <div id="research-preferences"><ResearchPreferencesSection settings={draft} update={update} /></div>
          <div id="signal-alerts"><SignalAlertPreferencesSection settings={draft} update={update} /></div>
          <div id="market-data"><MarketDataPreferencesSection settings={draft} update={update} /></div>
          <div id="display-interface"><DisplayInterfaceSection settings={draft} update={update} /></div>
          <div id="ai-research"><AIResearchSection settings={draft} update={update} /></div>
          <div id="privacy-data"><PrivacyDataSystemSection settings={draft} update={update} /></div>
        </div>
      </div>
    </main>
    <SettingsSaveBar dirty={dirty} saving={saving} resetting={resetting} status={status} error={error} onSave={() => void save()} onResetDraft={resetDraft} onResetDefaults={() => void resetDefaults()} />
    <footer className="settings-footer">Research and decision support only. No autonomous trading. Settings cannot bypass market-data validation or core analytical safeguards.</footer>
  </div>;
}
