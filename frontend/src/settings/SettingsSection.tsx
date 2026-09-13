import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";

export interface SettingsSectionProps {
  title: string;
  description: string;
  icon: LucideIcon;
  children: ReactNode;
  tone?: "default" | "danger";
}

export default function SettingsSection({ title, description, icon: Icon, children, tone = "default" }: SettingsSectionProps) {
  return <section className={`settings-section ${tone === "danger" ? "settings-section-danger" : ""}`}>
    <div className="settings-section-heading">
      <div className="settings-section-icon"><Icon size={18} /></div>
      <div><h3>{title}</h3><p>{description}</p></div>
    </div>
    <div className="settings-section-body">{children}</div>
  </section>;
}

export function SettingField({ label, description, children }: { label: string; description?: string; children: ReactNode }) {
  return <div className="setting-field"><div className="setting-field-copy"><strong>{label}</strong>{description && <span>{description}</span>}</div><div className="setting-field-control">{children}</div></div>;
}

export function Toggle({ checked, onChange, label = "Enabled" }: { checked: boolean; onChange: (value: boolean) => void; label?: string }) {
  return <label className="settings-toggle"><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} /><span className="toggle-track" aria-hidden="true"><span /></span><span>{label}</span></label>;
}

export function SelectField({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: readonly string[] }) {
  return <select className="settings-select" value={value} onChange={event => onChange(event.target.value)}>{options.map(option => <option key={option} value={option}>{option}</option>)}</select>;
}
