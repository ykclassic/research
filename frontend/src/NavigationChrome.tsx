import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, BrainCircuit, ChevronRight, LayoutDashboard, List, Menu, Network, Settings, ShieldCheck, X, LogOut } from "lucide-react";
import { getCurrentUser, logout, User } from "./api";

type NavItem = { label: string; page: string; route: string; icon: typeof LayoutDashboard };
type NavGroup = { label: string; items: NavItem[] };

const GROUPS: NavGroup[] = [
  { label: "Overview", items: [{ label: "Dashboard", page: "market", route: "/dashboard", icon: LayoutDashboard }] },
  { label: "Markets", items: [{ label: "Watchlists", page: "watchlists", route: "/markets/watchlists", icon: List }] },
  {
    label: "Analysis",
    items: [
      { label: "Technical Analysis", page: "analysis", route: "/analysis/technical", icon: BarChart3 },
      { label: "Market Structure", page: "market-structure", route: "/analysis/structure", icon: Network },
      { label: "Multi-Timeframe", page: "mtf", route: "/analysis/multi-timeframe", icon: BarChart3 },
      { label: "Signals", page: "signals", route: "/analysis/signals", icon: ShieldCheck },
    ],
  },
  { label: "Research", items: [{ label: "AI Market Research", page: "ai-research", route: "/research/ai", icon: BrainCircuit }] },
  { label: "System", items: [{ label: "Settings", page: "settings", route: "/settings", icon: Settings }] },
];

const routeByPage = new Map(GROUPS.flatMap(group => group.items.map(item => [item.page, item] as const)));
const pageByPath = new Map(GROUPS.flatMap(group => group.items.map(item => [item.route, item.page] as const)));

function currentPage(): string {
  return pageByPath.get(window.location.pathname) ?? "market";
}

function clickLegacyNavigation(page: string): boolean {
  if (page === "ai-research") {
    const trigger = document.querySelector<HTMLButtonElement>(".ai-tab-trigger");
    if (trigger) {
      trigger.click();
      return true;
    }
    return false;
  }
  if (page === "settings") return false;
  const labels: Record<string, string> = {
    market: "Market Data",
    watchlists: "Watchlists",
    analysis: "Technical Analysis",
    "market-structure": "Market Structure",
    mtf: "MTF Analysis",
    signals: "Signals",
  };
  const label = labels[page];
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>(".main-nav .nav-button"));
  const button = buttons.find(candidate => candidate.textContent?.trim() === label);
  if (!button) return false;
  button.click();
  return true;
}

export default function NavigationChrome() {
  const [user, setUser] = useState<User | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [page, setPage] = useState(currentPage);

  const syncFromLocation = useCallback(() => {
    const next = currentPage();
    setPage(next);
    if (next === "settings") {
      window.history.replaceState({}, "", "/dashboard");
      setPage("market");
      return;
    }
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (clickLegacyNavigation(next) || attempts >= 50) window.clearInterval(timer);
    }, 100);
  }, []);

  useEffect(() => {
    let active = true;
    const check = () => getCurrentUser().then(next => { if (active) setUser(next); }).catch(() => { if (active) setUser(null); });
    check();
    const timer = window.setInterval(check, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    window.addEventListener("popstate", syncFromLocation);
    syncFromLocation();
    return () => window.removeEventListener("popstate", syncFromLocation);
  }, [syncFromLocation]);

  const navigate = (item: NavItem) => {
    if (item.page === "settings") return;
    window.history.pushState({}, "", item.route);
    setPage(item.page);
    setMobileOpen(false);
    clickLegacyNavigation(item.page);
  };

  const signOut = async () => {
    try { await logout(); } finally { setUser(null); setMobileOpen(false); window.history.replaceState({}, "", "/dashboard"); clickLegacyNavigation("market"); }
  };

  const activeItem = useMemo(() => routeByPage.get(page) ?? routeByPage.get("market")!, [page]);
  if (!user) return null;

  return (
    <>
      <header className="app-chrome-header">
        <button className="chrome-menu" type="button" onClick={() => setMobileOpen(value => !value)} aria-label="Toggle navigation">
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <div className="chrome-heading">
          <div className="eyebrow">Adaptive Intelligence</div>
          <strong>{activeItem.label}</strong>
        </div>
        <div className="chrome-user">
          <span>{user.email}</span>
          <button type="button" className="chrome-signout" onClick={() => void signOut()}><LogOut size={15} /> Sign out</button>
        </div>
      </header>
      <aside className={`app-sidebar ${mobileOpen ? "open" : ""}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <div className="brand-mark"><BrainCircuit size={20} /></div>
          <div><div className="eyebrow">Adaptive</div><strong>Market Research</strong></div>
        </div>
        <nav className="sidebar-nav">
          {GROUPS.map(group => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map(item => {
                const Icon = item.icon;
                const active = page === item.page || (item.page === "market" && page === "market");
                const disabled = item.page === "settings";
                return <button key={item.page} type="button" className={`sidebar-item ${active ? "active" : ""} ${disabled ? "disabled" : ""}`} onClick={() => navigate(item)} disabled={disabled} title={disabled ? "Coming soon" : undefined}><Icon size={17} /><span>{item.label}</span>{disabled ? <span className="coming-soon">Soon</span> : active ? <ChevronRight size={15} /> : null}</button>;
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer"><ShieldCheck size={15} /><span>Validated research workspace</span></div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" type="button" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    </>
  );
}
