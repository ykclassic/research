import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, LogOut, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { ApiError, confirmPasswordReset, createWatchlist, deleteWatchlist, getCurrentUser, getQuotes, getWatchlists, login, logout, Quote, register, requestPasswordReset, removeWatchlistSymbol, User, Watchlist } from "./api";
import TechnicalAnalysisPage from "./TechnicalAnalysisPage";
import MarketStructurePage from "./MarketStructurePage";
import MTFAnalysisPage from "./MTFAnalysisPage";
import SignalPage from "./SignalPage";
import PortfolioPage from "./PortfolioPage";
import AIResearchPage from "./AIResearchPage";
import NewsResearchPage from "./NewsResearchPage";
import ResearchReportsPage from "./ResearchReportsPage";
import ResearchHistoryPage from "./ResearchHistoryPage";
import AlertsPage from "./AlertsPage";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
export type AppPage = "market" | "watchlists" | "analysis" | "market-structure" | "mtf" | "signals" | "portfolio" | "ai-research" | "news-research" | "research-reports" | "research-history" | "alerts";

type AuthMode = "login" | "register" | "forgot" | "reset";

const ROUTES: Record<AppPage, string> = {
  market: "/dashboard",
  watchlists: "/markets/watchlists",
  analysis: "/analysis/technical",
  "market-structure": "/analysis/structure",
  mtf: "/analysis/multi-timeframe",
  signals: "/analysis/signals",
  portfolio: "/portfolio",
  "ai-research": "/research/ai",
  "news-research": "/research/news",
  "research-reports": "/research/reports",
  "research-history": "/research/history",
  alerts: "/monitoring/alerts",
};

const PAGE_BY_ROUTE = new Map(Object.entries(ROUTES).map(([page, route]) => [route, page as AppPage]));

function pageFromPath(pathname: string): AppPage {
  return PAGE_BY_ROUTE.get(pathname) ?? "market";
}

function routeForPage(page: AppPage): string {
  return ROUTES[page];
}

function recoveryTokenFromLocation(): string | null {
  const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : window.location.hash;
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  return params.get("type") === "recovery" ? params.get("access_token") : null;
}

function formatPrice(v: number | null): string { return v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: v >= 1000 ? 2 : 6 }); }
function formatTime(v: string | null): string { return v ? new Date(v).toLocaleString() : "Unavailable"; }

function AuthScreen({ onAuthenticated }: { onAuthenticated: (u: User) => void }) {
  const recoveryToken = useMemo(() => recoveryTokenFromLocation(), []);
  const [mode, setMode] = useState<AuthMode>(recoveryToken ? "reset" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const switchMode = (next: AuthMode) => {
    setMode(next);
    setError(null);
    setNotice(null);
    setPassword("");
    setConfirmation("");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "login") {
        onAuthenticated(await login(email.trim(), password));
      } else if (mode === "register") {
        await register(email.trim(), password);
        setNotice("Account created successfully. Please sign in to continue.");
        setMode("login");
        setPassword("");
      } else if (mode === "forgot") {
        const message = await requestPasswordReset(email.trim());
        setNotice(message);
      } else {
        if (!recoveryToken) throw new ApiError("This password reset link is missing or invalid.", 400);
        if (password !== confirmation) throw new ApiError("The passwords do not match.", 400);
        await confirmPasswordReset(recoveryToken, password);
        window.history.replaceState({}, "", window.location.pathname);
        setNotice("Password updated successfully. You can now sign in with your new password.");
        setMode("login");
        setPassword("");
        setConfirmation("");
      }
    } catch (x) {
      setError(x instanceof Error ? x.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  };

  const title = mode === "login" ? "Welcome back" : mode === "register" ? "Create your account" : mode === "forgot" ? "Reset your password" : "Choose a new password";
  const submitLabel = mode === "login" ? "Sign in" : mode === "register" ? "Register" : mode === "forgot" ? "Send reset link" : "Update password";

  return <div className="auth-page"><div className="auth-card">
    <div className="eyebrow">Adaptive Intelligence</div>
    <h1>{title}</h1>
    {mode === "forgot" && <p className="auth-subtitle">Enter your account email and we will send a password reset link if the account exists.</p>}
    {mode === "reset" && <p className="auth-subtitle">Set a new password for your account. The reset link is single-use and expires.</p>}
    {error && <div className="error auth-error" role="alert"><AlertTriangle size={17}/>{error}</div>}
    {notice && <div className="auth-success" role="status">{notice}</div>}
    <form className="auth-form" onSubmit={submit}>
      {mode !== "reset" && <label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required autoComplete={mode === "login" ? "email" : "email"}/></label>}
      {mode !== "forgot" && <label>Password<input type="password" minLength={8} value={password} onChange={e=>setPassword(e.target.value)} required autoComplete={mode === "login" ? "current-password" : "new-password"}/></label>}
      {mode === "reset" && <label>Confirm password<input type="password" minLength={8} value={confirmation} onChange={e=>setConfirmation(e.target.value)} required autoComplete="new-password"/></label>}
      <button className="auth-submit" disabled={busy}>{busy ? "Please wait…" : submitLabel}</button>
    </form>
    {mode === "login" && <>
      <button className="auth-switch" onClick={()=>switchMode("forgot")}>Forgot password?</button>
      <button className="auth-switch" onClick={()=>switchMode("register")}>Need an account? Register</button>
    </>}
    {mode === "register" && <button className="auth-switch" onClick={()=>switchMode("login")}>Already registered? Sign in</button>}
    {mode === "forgot" && <button className="auth-switch" onClick={()=>switchMode("login")}>Return to sign in</button>}
    {mode === "reset" && <button className="auth-switch" onClick={()=>switchMode("login")}>Return to sign in</button>}
  </div></div>;
}

function Header({ user, page, setPage, onLogout }: { user: User; page: AppPage; setPage: (p: AppPage) => void; onLogout: () => void }) {
  const signOut = async () => { try { await logout(); } finally { onLogout(); } };
  const items: [AppPage,string][] = [["market","Market Data"],["watchlists","Watchlists"],["analysis","Technical Analysis"],["market-structure","Market Structure"],["mtf","MTF Analysis"],["signals","Signals"],["portfolio","Portfolio"]];
  return <header className="topbar"><div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div><nav className="main-nav" aria-label="Research sections">{items.map(([id,label])=><button key={id} className={`nav-button ${page===id?"active":""}`} onClick={()=>setPage(id)}>{label}</button>)}</nav><div className="topbar-actions"><span className="user-email">{user.email}</span><button className="logout" onClick={()=>void signOut()}><LogOut size={16}/>Sign out</button></div></header>;
}

function MarketPage({ user, onLogout, setPage }: { user: User; onLogout: ()=>void; setPage:(p:AppPage)=>void }) {
  const [quotes,setQuotes]=useState<Quote[]>([]); const [error,setError]=useState<string|null>(null); const [refreshing,setRefreshing]=useState(false);
  const load=useCallback(async(force=false)=>{try{setError(null);if(force)setRefreshing(true);setQuotes(await getQuotes(SYMBOLS,force));}catch(e){if(e instanceof ApiError&&e.status===401){onLogout();return;}setError(e instanceof Error?e.message:"Unable to retrieve market data.");}finally{setRefreshing(false);}},[onLogout]);
  useEffect(()=>{void load();},[load]);
  return <div className="app"><Header user={user} page="market" setPage={setPage} onLogout={onLogout}/><main><section className="hero dashboard-hero"><div><div className="eyebrow">Phase 1 · Live market data</div><h2>Validated market snapshots.</h2><p>Only provider-validated quotes are presented as current market data.</p></div><div className="hero-stat"><ShieldCheck size={20}/><strong>{quotes.filter(q=>q.status==="LIVE").length}</strong><span>live quotes</span></div></section>{error&&<div className="error"><AlertTriangle size={17}/>{error}</div>}<section className="panel dashboard-market-panel"><div className="panel-head"><div><h3>Market scanner</h3><span>Provider timestamp and provenance are preserved.</span></div><button className="refresh" onClick={()=>void load(true)} disabled={refreshing}><RefreshCw size={16}/>{refreshing?"Refreshing":"Refresh prices"}</button></div><div className="quotes">{quotes.map(q=><div className="quote-row" key={q.symbol}><div className="symbol">{q.symbol}</div><div className="price">{formatPrice(q.price)}</div><div className={`status ${q.status.toLowerCase()}`}><span className="dot"/>{q.status}</div><div className="timestamp">{q.source??"—"} · {formatTime(q.timestamp)}</div></div>)}</div></section><footer>Research and decision support only. No autonomous trading.</footer></main></div>;
}

function WatchlistsPage({ user, onLogout, setPage }: { user: User; onLogout: ()=>void; setPage:(p:AppPage)=>void }) {
  const [lists,setLists]=useState<Watchlist[]>([]); const [active,setActive]=useState<string|null>(null); const [error,setError]=useState<string|null>(null); const [name,setName]=useState(""); const [symbol,setSymbol]=useState(SYMBOLS[0]);
  const load=useCallback(async()=>{try{const next=await getWatchlists();setLists(next);setActive(cur=>next.some(w=>w.id===cur)?cur:next[0]?.id??null);}catch(e){if(e instanceof ApiError&&e.status===401)onLogout();else setError(e instanceof Error?e.message:"Unable to load watchlists.");}},[onLogout]);
  useEffect(()=>{void load();},[load]); const current=lists.find(w=>w.id===active)??lists[0];
  const add=async()=>{if(!name.trim())return;try{await createWatchlist(name.trim());setName("");await load();}catch(e){setError(e instanceof Error?e.message:"Unable to create watchlist.");}};
  const remove=async(id:string)=>{try{await deleteWatchlist(id);await load();}catch(e){setError(e instanceof Error?e.message:"Unable to delete watchlist.");}};
  const removeSymbol=async(s:string)=>{if(!current)return;try{await removeWatchlistSymbol(current.id,s);await load();}catch(e){setError(e instanceof Error?e.message:"Unable to remove symbol.");}};
  return <div className="app"><Header user={user} page="watchlists" setPage={setPage} onLogout={onLogout}/><main><section className="hero"><div><div className="eyebrow">Phase 2 · Watchlists</div><h2>Persistent research lists.</h2><p>Watchlists are isolated to the authenticated account.</p></div></section>{error&&<div className="error"><AlertTriangle size={17}/>{error}</div>}<section className="workspace-grid"><aside className="panel"><div className="panel-head"><h3>Watchlists</h3></div><div className="inline-form"><input placeholder="New watchlist" value={name} onChange={e=>setName(e.target.value)}/><button onClick={()=>void add()}><Plus size={15}/>Create</button></div>{lists.map(w=><div className="quote-row" key={w.id}><button className="watchlist-select" onClick={()=>setActive(w.id)}>{w.name} ({w.watchlist_items.length})</button><button className="icon-button danger" onClick={()=>void remove(w.id)}><Trash2 size={14}/></button></div>)}</aside><section className="panel"><div className="panel-head"><div><h3>{current?.name??"Select a watchlist"}</h3><span>Symbols</span></div>{current&&<div className="inline-form"><select value={symbol} onChange={e=>setSymbol(e.target.value)}>{SYMBOLS.map(s=><option key={s}>{s}</option>)}</select><button onClick={()=>void (async()=>{try{const {addWatchlistSymbol}=await import("./api");await addWatchlistSymbol(current.id,symbol);await load();}catch(e){setError(e instanceof Error?e.message:"Unable to add symbol.");}})()}><Plus size={15}/>Add</button></div>}</div>{current?.watchlist_items.map(i=><div className="quote-row" key={i.id}><div className="symbol">{i.symbol}</div><button className="icon-button danger" onClick={()=>void removeSymbol(i.symbol)}><Trash2 size={14}/></button></div>)}</section></section><footer>Research and decision support only.</footer></main></div>;
}

function App(){
  const [user,setUser]=useState<User|null>(null);
  const [checking,setChecking]=useState(true);
  const [page,setPage]=useState<AppPage>(()=>pageFromPath(window.location.pathname));

  const navigate=useCallback((next:AppPage, replace=false)=>{
    const target=routeForPage(next);
    if(window.location.pathname!==target){
      if(replace) window.history.replaceState({},"",target); else window.history.pushState({},"",target);
    }
    setPage(next);
    window.scrollTo({top:0,behavior:"auto"});
  },[]);

  const onLogout=useCallback(()=>{setUser(null);navigate("market",true);},[navigate]);

  useEffect(()=>{
    const handlePopState=()=>setPage(pageFromPath(window.location.pathname));
    window.addEventListener("popstate",handlePopState);
    return()=>window.removeEventListener("popstate",handlePopState);
  },[]);

  useEffect(()=>{
    let active=true;
    getCurrentUser().then(next=>{if(active)setUser(next);}).catch(()=>{if(active)setUser(null);}).finally(()=>{if(active)setChecking(false);});
    return()=>{active=false;};
  },[]);

  useEffect(()=>{
    if(checking)return;
    const recovery=recoveryTokenFromLocation();
    if(!recovery && window.location.pathname!==routeForPage(page) && !window.location.hash) navigate(page,true);
  },[checking,navigate,page]);

  if(checking)return <div className="auth-loading">Checking session…</div>;
  if(!user)return <AuthScreen onAuthenticated={(next)=>{setUser(next);navigate("market",true);}}/>;

  if(page==="market")return <MarketPage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="watchlists")return <WatchlistsPage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="analysis")return <TechnicalAnalysisPage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="market-structure")return <MarketStructurePage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="mtf")return <MTFAnalysisPage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="signals")return <SignalPage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="portfolio")return <PortfolioPage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="ai-research")return <AIResearchPage user={user} onLogout={onLogout} setPage={navigate}/>;
  if(page==="news-research")return <NewsResearchPage onLogout={onLogout}/>;
  if(page==="research-reports")return <ResearchReportsPage/>;
  if(page==="research-history")return <ResearchHistoryPage/>;
  return <AlertsPage/>;
}

export default App;
