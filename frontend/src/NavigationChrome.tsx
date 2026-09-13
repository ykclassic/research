import { useEffect, useState } from "react";
import { BarChart3, Bell, BrainCircuit, ChevronRight, FileText, History, LayoutDashboard, List, Menu, Network, Settings, ShieldCheck, X, LogOut, Newspaper, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { getCurrentUser, logout, User } from "./api";

const GROUPS = [
  { label: "Overview", items: [{ label: "Dashboard", page: "market", route: "/dashboard", icon: LayoutDashboard }] },
  { label: "Markets", items: [{ label: "Watchlists", page: "watchlists", route: "/markets/watchlists", icon: List }] },
  { label: "Analysis", items: [
    { label: "Technical Analysis", page: "analysis", route: "/analysis/technical", icon: BarChart3 },
    { label: "Market Structure", page: "market-structure", route: "/analysis/structure", icon: Network },
    { label: "Multi-Timeframe", page: "mtf", route: "/analysis/multi-timeframe", icon: BarChart3 },
    { label: "Signals", page: "signals", route: "/analysis/signals", icon: ShieldCheck },
  ] },
  { label: "Research", items: [
    { label: "AI Market Research", page: "ai-research", route: "/research/ai", icon: BrainCircuit },
    { label: "News & Fundamentals", page: "news-research", route: "/research/news", icon: Newspaper },
    { label: "Research Reports", page: "research-reports", route: "/research/reports", icon: FileText },
    { label: "Research History", page: "research-history", route: "/research/history", icon: History },
  ] },
  { label: "Monitoring", items: [{ label: "Alerts & Monitoring", page: "alerts", route: "/monitoring/alerts", icon: Bell }] },
  { label: "System", items: [{ label: "Settings", page: "settings", route: "/settings", icon: Settings }] },
] as const;

type NavItem = (typeof GROUPS)[number]["items"][number];
const pageByPath = new Map(GROUPS.flatMap(group => group.items.map(item => [item.route, item.page] as const)));

function currentPage(): string {
  return pageByPath.get(window.location.pathname) ?? "market";
}

export default function NavigationChrome() {
  const [user, setUser] = useState<User | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 900);
  const [collapsed, setCollapsed] = useState(() => {
    try { return window.localStorage.getItem("research-sidebar-collapsed") === "true"; } catch { return false; }
  });
  const [page, setPage] = useState(currentPage);

  useEffect(() => {
    let active = true;
    const check = () => getCurrentUser().then(next => { if (active) setUser(next); }).catch(() => { if (active) setUser(null); });
    check();
    const timer = window.setInterval(check, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    const sync = () => setPage(currentPage());
    const handleResize = () => setIsMobile(window.innerWidth <= 900);
    window.addEventListener("popstate", sync);
    window.addEventListener("resize", handleResize);
    sync();
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  useEffect(() => {
    try { window.localStorage.setItem("research-sidebar-collapsed", String(collapsed)); } catch { /* localStorage may be unavailable */ }
    document.body.classList.toggle("sidebar-collapsed", collapsed && !isMobile);
    return () => document.body.classList.remove("sidebar-collapsed");
  }, [collapsed, isMobile]);

  const navigate = (item: NavItem) => {
    if (item.page === "settings") return;
    if (window.location.pathname !== item.route) window.history.pushState({}, "", item.route);
    setPage(item.page);
    setMobileOpen(false);
    window.dispatchEvent(new PopStateEvent("popstate"));
    window.scrollTo({ top: 0, behavior: "auto" });
  };

  const signOut = async () => {
    try { await logout(); } finally {
      setUser(null);
      setMobileOpen(false);
      window.history.replaceState({}, "", "/dashboard");
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
  };

  const activeItem = GROUPS.flatMap(group => group.items).find(item => item.page === page) ?? GROUPS[0].items[0];
  if (!user) return null;

  return <>
    <header className={`app-chrome-header ${collapsed && !isMobile ? "sidebar-collapsed" : ""}`}>
      <button className="chrome-menu" type="button" onClick={() => isMobile ? setMobileOpen(value => !value) : setCollapsed(value => !value)} aria-label={isMobile ? "Toggle navigation" : collapsed ? "Expand navigation" : "Collapse navigation"} title={isMobile ? "Toggle navigation" : collapsed ? "Expand sidebar" : "Collapse sidebar"}>
        {isMobile ? (mobileOpen ? <X size={20} /> : <Menu size={20} />) : (collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />)}
      </button>
      <div className="chrome-heading"><div className="eyebrow">Adaptive Intelligence</div><strong>{activeItem.label}</strong></div>
      <div className="chrome-user"><span>{user.email}</span><button type="button" className="chrome-signout" onClick={() => void signOut()}><LogOut size={15} /> Sign out</button></div>
    </header>
    <aside className={`app-sidebar ${collapsed && !isMobile ? "collapsed" : ""} ${mobileOpen ? "open" : ""}`} aria-label="Primary navigation">
      <div className="sidebar-brand"><div className="brand-mark"><BrainCircuit size={20} /></div><div className="sidebar-brand-copy"><div className="eyebrow">Adaptive</div><strong>Market Research</strong></div></div>
      <nav className="sidebar-nav">
        {GROUPS.map(group => <div className="nav-group" key={group.label}>
          <div className="nav-group-label">{group.label}</div>
          {group.items.map(item => {
            const Icon = item.icon;
            const active = page === item.page;
            const disabled = item.page === "settings";
            return <button key={item.page} type="button" className={`sidebar-item ${active ? "active" : ""} ${disabled ? "disabled" : ""}`} onClick={() => navigate(item)} disabled={disabled} title={disabled ? "Coming soon" : collapsed && !isMobile ? item.label : undefined}>
              <Icon size={17} /><span>{item.label}</span>{disabled ? <span className="coming-soon">Soon</span> : active ? <ChevronRight size={15} /> : null}
            </button>;
          })}
        </div>)}
      </nav>
      <div className="sidebar-footer"><ShieldCheck size={15} /><span>Validated research workspace</span></div>
    </aside>
    {mobileOpen && <button className="sidebar-backdrop" type="button" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
  </>;
}
