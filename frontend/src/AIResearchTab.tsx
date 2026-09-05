import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { getCurrentUser, ApiError, User } from "./api";
import AIResearchPage from "./AIResearchPage";

export default function AIResearchTab() {
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let active = true;
    getCurrentUser().then(next => { if (active) setUser(next); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (!user) return null;

  const logout = () => setUser(null);
  const setPage = () => setOpen(false);

  return <>
    {!open && <button className="ai-tab-trigger" onClick={() => setOpen(true)} aria-label="Open AI Market Research">AI Market Research</button>}
    {open && <div className="ai-tab-overlay"><button className="ai-tab-close" onClick={() => setOpen(false)} aria-label="Close AI Market Research"><X size={18}/></button><AIResearchPage user={user} onLogout={logout} setPage={setPage}/></div>}
  </>;
}
