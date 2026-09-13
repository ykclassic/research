import { useState } from "react";
import { AlertTriangle, KeyRound, LogOut, ShieldCheck, Trash2, UserRound } from "lucide-react";
import type { AccountInfo } from "../settingsApi";
import { changePassword, deleteAccount, deleteAllWatchlists, deleteResearchHistory, requestAccountPasswordReset, signOutAllSessions, signOutOtherSessions } from "../settingsApi";
import { SettingField, SettingsSection } from "./SettingsSection";

function formatDate(value: string | null): string {
  if (!value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : date.toLocaleString();
}

interface Props {
  account: AccountInfo;
  onLogout: () => void;
}

export default function AccountSecuritySection({ account, onLogout }: Props) {
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  const run = async (key: string, action: () => Promise<unknown>, success: string) => {
    setBusy(key); setError(null); setMessage(null);
    try { await action(); setMessage(success); }
    catch (value) { setError(value instanceof Error ? value.message : "The action failed."); }
    finally { setBusy(null); }
  };

  const submitPassword = async () => {
    if (newPassword !== confirmPassword) { setError("The new passwords do not match."); return; }
    if (newPassword.length < 8) { setError("The new password must contain at least 8 characters."); return; }
    await run("password", async () => { await changePassword(currentPassword, newPassword); setPasswordOpen(false); setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); }, "Password updated successfully.");
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirmation !== "DELETE") { setError("Type DELETE exactly to permanently delete the account."); return; }
    setBusy("account-delete"); setError(null);
    try { await deleteAccount(); onLogout(); }
    catch (value) { setError(value instanceof Error ? value.message : "Account deletion failed."); setBusy(null); }
  };

  return <>
    <SettingsSection title="Account" description="Identity and account status managed by the authentication service." icon={UserRound}>
      <div className="settings-info-grid">
        <div><span>Email address</span><strong>{account.email}</strong></div>
        <div><span>Account creation date</span><strong>{formatDate(account.created_at)}</strong></div>
        <div><span>Account status</span><strong className="settings-status-ok">● {account.account_status === "active" ? "Active" : "Email unconfirmed"}</strong></div>
        <div><span>Last login</span><strong>{formatDate(account.last_sign_in_at)}</strong></div>
      </div>
      <SettingField label="Sign out of all sessions" description="Revoke all Supabase refresh sessions, including this browser.">
        <button className="settings-secondary-button danger-outline" disabled={busy !== null} onClick={() => void run("all-sessions", async () => { await signOutAllSessions(); onLogout(); }, "All sessions have been signed out.")}><LogOut size={15} />{busy === "all-sessions" ? "Signing out…" : "Sign out all sessions"}</button>
      </SettingField>
    </SettingsSection>

    <SettingsSection title="Security" description="Manage your password and active authentication sessions." icon={ShieldCheck}>
      <SettingField label="Change password" description="Enter your current password and choose a new password.">
        <button className="settings-secondary-button" onClick={() => { setPasswordOpen(value => !value); setError(null); setMessage(null); }}><KeyRound size={15} />{passwordOpen ? "Close" : "Change password"}</button>
      </SettingField>
      {passwordOpen && <div className="settings-inline-form">
        <label>Current password<input type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} autoComplete="current-password" /></label>
        <label>New password<input type="password" minLength={8} value={newPassword} onChange={event => setNewPassword(event.target.value)} autoComplete="new-password" /></label>
        <label>Confirm new password<input type="password" minLength={8} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} autoComplete="new-password" /></label>
        <button className="settings-primary-button" disabled={busy !== null} onClick={() => void submitPassword()}>{busy === "password" ? "Updating…" : "Update password"}</button>
      </div>}
      <SettingField label="Password reset" description="Send a secure reset link to the account email address.">
        <button className="settings-secondary-button" disabled={busy !== null} onClick={() => void run("reset", async () => { await requestAccountPasswordReset(account.email); }, "If the account can receive mail, a password reset link has been requested.")}>{busy === "reset" ? "Sending…" : "Send reset link"}</button>
      </SettingField>
      <SettingField label="Session management" description="Keep this browser session active while revoking other sessions.">
        <button className="settings-secondary-button" disabled={busy !== null} onClick={() => void run("other-sessions", async () => { await signOutOtherSessions(); }, "All other active sessions have been signed out.")}>{busy === "other-sessions" ? "Signing out…" : "Sign out other sessions"}</button>
      </SettingField>
      <div className="settings-session-card"><div><strong>Current session</strong><span>This browser · active now</span></div><span className="settings-session-active">● Active</span></div>
      <div className="settings-future-note"><KeyRound size={15} /><span><strong>2FA</strong> — Reserved for a future MFA phase. It is not represented as enabled until the authentication backend supports enrollment and recovery.</span></div>
    </SettingsSection>

    <SettingsSection title="Danger zone" description="Destructive actions permanently remove user-owned data." icon={Trash2} tone="danger">
      <div className="settings-danger-warning"><AlertTriangle size={17} /><span>These actions cannot be undone. Account deletion also removes all user-owned application data through database cascades.</span></div>
      <SettingField label="Delete research history" description="Permanently remove saved reports, searches and AI analyses for this account.">
        <button className="settings-secondary-button danger-outline" disabled={busy !== null} onClick={() => { if (window.confirm("Delete all research history? This cannot be undone.")) void run("history-delete", async () => { await deleteResearchHistory(); }, "Research history deleted."); }}>{busy === "history-delete" ? "Deleting…" : "Delete research history"}</button>
      </SettingField>
      <SettingField label="Delete all watchlists" description="Permanently remove every watchlist and its symbols.">
        <button className="settings-secondary-button danger-outline" disabled={busy !== null} onClick={() => { if (window.confirm("Delete all watchlists? This cannot be undone.")) void run("watchlist-delete", async () => { await deleteAllWatchlists(); }, "All watchlists deleted."); }}>{busy === "watchlist-delete" ? "Deleting…" : "Delete all watchlists"}</button>
      </SettingField>
      <SettingField label="Permanent account deletion" description="Delete the authentication account, saved preferences and all cascading user-owned data.">
        <button className="settings-secondary-button danger-button" disabled={busy !== null} onClick={() => { setDeleteOpen(true); setDeleteConfirmation(""); setError(null); setMessage(null); }}>Delete account</button>
      </SettingField>
      {deleteOpen && <div className="settings-delete-confirmation">
        <h4>Delete Account</h4>
        <p>This permanently deletes your account, research history, reports, watchlists and saved preferences. This action cannot be undone.</p>
        <label>Type DELETE to continue<input value={deleteConfirmation} onChange={event => setDeleteConfirmation(event.target.value)} autoComplete="off" /></label>
        <div className="settings-confirm-actions"><button className="settings-secondary-button" disabled={busy !== null} onClick={() => setDeleteOpen(false)}>Cancel</button><button className="settings-secondary-button danger-button" disabled={busy !== null || deleteConfirmation !== "DELETE"} onClick={() => void handleDeleteAccount()}>{busy === "account-delete" ? "Deleting account…" : "Delete account permanently"}</button></div>
      </div>}
      {message && <div className="settings-inline-success" role="status">{message}</div>}
      {error && <div className="settings-inline-error" role="alert">{error}</div>}
    </SettingsSection>
  </>;
}
