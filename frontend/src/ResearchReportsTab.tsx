import { useState } from "react";
import ResearchReportsPage from "./ResearchReportsPage";
import "./research-reports-tab.css";

export default function ResearchReportsTab() {
  const [open, setOpen] = useState(false);
  return <>
    <button className="research-reports-tab-trigger" type="button" onClick={() => setOpen(true)}>Research Reports</button>
    {open && <div className="research-reports-overlay"><button className="research-reports-close" type="button" aria-label="Close research reports" onClick={() => setOpen(false)}>×</button><ResearchReportsPage /></div>}
  </>;
}
