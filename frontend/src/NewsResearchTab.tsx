import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { getCurrentUser, User } from "./api";
import NewsResearchPage from "./NewsResearchPage";

export default function NewsResearchTab() {
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let active = true;
    const check = () => getCurrentUser().then(next => { if (active) setUser(next); }).catch(() => { if (active) setUser(null); });
    check();
    const timer = window.setInterval(check, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  if (!user) return null;
  const logout = () => { setUser(null); setOpen(false); };
  return <>{!open && <button className="news-tab-trigger" onClick={() => setOpen(true)} aria-label="Open News and Fundamental Research">News & Fundamentals</button>}{open && <div className="news-tab-overlay"><button className="news-tab-close" onClick={() => setOpen(false)} aria-label="Close News and Fundamental Research"><X size={18}/></button><NewsResearchPage onLogout={logout}/></div>}</>;
}
