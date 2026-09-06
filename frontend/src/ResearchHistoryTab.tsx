import { useState } from "react";
import ResearchHistoryPage from "./ResearchHistoryPage";

export default function ResearchHistoryTab() {
  const [open, setOpen] = useState(false);
  return <>
    <button className="research-history-tab-trigger" type="button" onClick={() => setOpen(true)}>Research History</button>
    {open && <div className="research-history-overlay"><button className="research-history-close" type="button" aria-label="Close research history" onClick={() => setOpen(false)}>×</button><ResearchHistoryPage /></div>}
  </>;
}
