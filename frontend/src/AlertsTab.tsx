import { useEffect, useState } from "react";
import AlertsPage from "./AlertsPage";

export default function AlertsTab() {
  const [open, setOpen] = useState(false);
  useEffect(() => { const handler = () => setOpen(true); window.addEventListener("open-alerts", handler); return () => window.removeEventListener("open-alerts", handler); }, []);
  if (!open) return null;
  return <div className="alerts-tab-overlay"><AlertsPage onClose={() => setOpen(false)} /></div>;
}
