import { Check, RotateCcw, Save, X } from "lucide-react";

interface Props {
  dirty: boolean;
  saving: boolean;
  resetting: boolean;
  status: string | null;
  error: string | null;
  onSave: () => void;
  onResetDraft: () => void;
  onResetDefaults: () => void;
}

export default function SettingsSaveBar({ dirty, saving, resetting, status, error, onSave, onResetDraft, onResetDefaults }: Props) {
  return <div className="settings-save-bar">
    <div className="settings-save-status">
      {error ? <><X size={15} />{error}</> : status ? <><Check size={15} />{status}</> : dirty ? "You have unsaved changes." : "All settings are saved."}
    </div>
    <div className="settings-save-actions">
      <button className="settings-secondary-button" disabled={!dirty || saving || resetting} onClick={onResetDraft}><RotateCcw size={15} />Discard changes</button>
      <button className="settings-secondary-button" disabled={saving || resetting} onClick={onResetDefaults}><RotateCcw size={15} />Reset to defaults</button>
      <button className="settings-primary-button" disabled={!dirty || saving || resetting} onClick={onSave}><Save size={15} />{saving ? "Saving…" : "Save changes"}</button>
    </div>
  </div>;
}
