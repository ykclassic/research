import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Check,
  Clock3,
  LogOut,
  Plus,
  RefreshCw,
  ShieldCheck,
  Star,
  Trash2,
  Pencil,
  X,
} from "lucide-react";
import {
  ApiError,
  addWatchlistSymbol,
  confirmPasswordReset,
  createWatchlist,
  deleteWatchlist,
  getCurrentUser,
  getQuotes,
  getWatchlists,
  login,
  logout,
  Quote,
  register,
  removeWatchlistSymbol,
  renameWatchlist,
  requestPasswordReset,
  User,
  Watchlist,
} from "./api";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
type AuthMode = "login" | "register" | "forgot" | "reset";

function formatPrice(price: number | null): string {
  if (price === null) return "—";
  if (price >= 1000) return price.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (price >= 1) return price.toLocaleString(undefined, { maximumFractionDigits: 5 });
  return price.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function formatTime(timestamp: string | null): string {
  if (!timestamp) return "No timestamp";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";
  return date.toLocaleTimeString();
}

function statusClass(status: Quote["status"]): string {
  if (status === "LIVE") return "live";
  if (status === "MARKET_CLOSED") return "closed";
  if (status === "STALE") return "stale";
  return "unavailable";
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = hash.get("access_token");
    const recovery = hash.get("type") === "recovery" || params.get("reset") === "1";
    if (token && recovery) {
      setResetToken(token);
      setMode("reset");
      setError(null);
      setSuccess(null);
    } else if (params.get("reset") === "1") {
      setMode("forgot");
    }
  }, []);

  const clearRecoveryUrl = () => window.history.replaceState({}, document.title, window.location.pathname);

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError(null);
    setSuccess(null);
    setPassword("");
    setConfirmPassword("");
    if (nextMode !== "reset") setResetToken(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if ((mode === "register" || mode === "reset") && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "login") {
        const user = await login(email.trim(), password);
        onAuthenticated(user);
        return;
      }
      if (mode === "register") {
        await register(email.trim(), password);
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setSuccess("Registration successful. Please sign in with your new account.");
        return;
      }
      if (mode === "forgot") {
        const message = await requestPasswordReset(email.trim());
        setSuccess(message);
        return;
      }
      if (!resetToken) {
        setError("Password reset link is missing or invalid.");
        return;
      }
      const message = await confirmPasswordReset(resetToken, password);
      clearRecoveryUrl();
      setResetToken(null);
      setMode("login");
      setPassword("");
      setConfirmPassword("");
      setSuccess(message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  };

  const title = mode === "login" ? "Welcome back" : mode === "register" ? "Create your account" : mode === "forgot" ? "Reset your password" : "Choose a new password";
  const subtitle = mode === "login"
    ? "Sign in to access validated market research."
    : mode === "register"
      ? "Create an account to access the research dashboard."
      : mode === "forgot"
        ? "Enter your account email and we will send a secure reset link."
        : "Enter a new password for your account.";

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="eyebrow">Adaptive Intelligence</div>
        <h1>{title}</h1>
        <p className="auth-subtitle">{subtitle}</p>
        {success && <div className="auth-success" role="status">{success}</div>}
        {error && <div className="error auth-error" role="alert"><AlertTriangle size={17} />{error}</div>}
        <form onSubmit={submit} className="auth-form">
          {(mode === "login" || mode === "register" || mode === "forgot") && (
            <label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          )}
          {(mode === "login" || mode === "register" || mode === "reset") && (
            <label>Password<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required /></label>
          )}
          {(mode === "register" || mode === "reset") && (
            <label>Confirm password<input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={8} required /></label>
          )}
          <button className="auth-submit" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : mode === "register" ? "Register" : mode === "forgot" ? "Send reset link" : "Update password"}</button>
        </form>
        {mode === "login" && <button className="auth-switch" type="button" onClick={() => switchMode("forgot")}>Forgot your password?</button>}
        {mode === "login" && <button className="auth-switch" type="button" onClick={() => switchMode("register")}>Need an account? Register</button>}
        {mode === "register" && <button className="auth-switch" type="button" onClick={() => switchMode("login")}>Already registered? Sign in</button>}
        {mode === "forgot" && <button className="auth-switch" type="button" onClick={() => switchMode("login")}>Back to Sign in</button>}
        {mode === "reset" && <button className="auth-switch" type="button" onClick={() => { clearRecoveryUrl(); switchMode("login"); }}>Back to Sign in</button>}
      </div>
    </div>
  );
}

function Dashboard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [activeWatchlistId, setActiveWatchlistId] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loadingWorkspace, setLoadingWorkspace] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newWatchlistName, setNewWatchlistName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [symbolToAdd, setSymbolToAdd] = useState(SYMBOLS[0]);
  const [search, setSearch] = useState("");
  const requestInFlight = useRef(false);
  const refreshSecondsRaw = Number(import.meta.env.VITE_QUOTE_REFRESH_SECONDS ?? 60);
  const refreshSeconds = Number.isFinite(refreshSecondsRaw) && refreshSecondsRaw >= 10 ? refreshSecondsRaw : 60;

  const activeWatchlist = useMemo(() => watchlists.find((item) => item.id === activeWatchlistId) ?? watchlists[0] ?? null, [activeWatchlistId, watchlists]);
  const activeSymbols = activeWatchlist?.watchlist_items.map((item) => item.symbol) ?? [];
  const selectedQuote = useMemo(() => quotes.find((quote) => quote.symbol === selected), [quotes, selected]);
  const availableSymbols = useMemo(() => {
    const query = search.trim().toUpperCase();
    return SYMBOLS.filter((symbol) => !query || symbol.includes(query));
  }, [search]);

  const loadWorkspace = useCallback(async () => {
    setLoadingWorkspace(true);
    try {
      const next = await getWatchlists();
      setWatchlists(next);
      setActiveWatchlistId((current) => next.some((item) => item.id === current) ? current : next[0]?.id ?? null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "Unable to load your watchlists.");
    } finally {
      setLoadingWorkspace(false);
    }
  }, [onLogout]);

  const loadQuotes = useCallback(async (symbols: string[], force = false) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      if (force) setRefreshing(true);
      const nextQuotes = symbols.length ? await getQuotes(symbols, force) : [];
      setQuotes(nextQuotes);
      setSelected((current) => current && nextQuotes.some((quote) => quote.symbol === current) ? current : nextQuotes[0]?.symbol ?? null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "Unable to retrieve market data.");
    } finally {
      requestInFlight.current = false;
      setRefreshing(false);
    }
  }, [onLogout]);

  useEffect(() => { void loadWorkspace(); }, [loadWorkspace]);

  useEffect(() => {
    void loadQuotes(activeSymbols, false);
    const timer = window.setInterval(() => {
      if (activeSymbols.length) void loadQuotes(activeSymbols, false);
    }, refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [activeSymbols.join(","), refreshSeconds, loadQuotes]);

  const runAction = async (key: string, operation: () => Promise<void>) => {
    setAction(key);
    setError(null);
    setNotice(null);
    try {
      await operation();
      await loadWorkspace();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "The requested action failed.");
    } finally {
      setAction(null);
    }
  };

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = newWatchlistName.trim();
    if (!name) return;
    await runAction("create", async () => {
      const created = await createWatchlist(name);
      setNewWatchlistName("");
      setShowCreate(false);
      setActiveWatchlistId(created.id);
      setNotice(`Created ${created.name}.`);
    });
  };

  const handleRename = async (id: string) => {
    const name = editingName.trim();
    if (!name) return;
    await runAction(`rename:${id}`, async () => {
      await renameWatchlist(id, name);
      setEditingId(null);
      setEditingName("");
      setNotice("Watchlist renamed.");
    });
  };

  const handleDelete = async (watchlist: Watchlist) => {
    if (watchlists.length === 1) {
      setError("Keep at least one watchlist in your workspace.");
      return;
    }
    if (!window.confirm(`Delete ${watchlist.name}? Its symbols will also be removed.`)) return;
    await runAction(`delete:${watchlist.id}`, async () => {
      await deleteWatchlist(watchlist.id);
      setNotice(`${watchlist.name} deleted.`);
    });
  };

  const handleAddSymbol = async () => {
    if (!activeWatchlist) return;
    if (activeSymbols.includes(symbolToAdd)) {
      setError(`${symbolToAdd} is already in ${activeWatchlist.name}.`);
      return;
    }
    await runAction(`add:${symbolToAdd}`, async () => {
      await addWatchlistSymbol(activeWatchlist.id, symbolToAdd);
      setSelected(symbolToAdd);
      setNotice(`${symbolToAdd} added to ${activeWatchlist.name}.`);
    });
  };

  const handleRemoveSymbol = async (symbol: string) => {
    if (!activeWatchlist) return;
    await runAction(`remove:${symbol}`, async () => {
      await removeWatchlistSymbol(activeWatchlist.id, symbol);
      setNotice(`${symbol} removed.`);
    });
  };

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      onLogout();
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div><div className="eyebrow">Adaptive Intelligence</div><h1>Market Research</h1></div>
        <div className="topbar-actions">
          <span className="user-email">{user.email}</span>
          <button className="logout" onClick={() => void handleLogout()}><LogOut size={16} />Sign out</button>
          <button className="refresh" onClick={() => void loadQuotes(activeSymbols, true)} disabled={refreshing || activeSymbols.length === 0}><RefreshCw size={16} className={refreshing ? "spin" : ""} />{refreshing ? "Refreshing" : "Refresh prices"}</button>
        </div>
      </header>

      <main>
        <section className="hero">
          <div><div className="eyebrow">Market workspace</div><h2>Your research universe, persisted to your account.</h2><p>Watchlists belong to the authenticated user. Quotes continue to come from the existing validated server-side market-data service.</p></div>
          <div className="hero-stat"><Activity size={20} /><strong>{quotes.filter((q) => q.status === "LIVE").length}/{activeSymbols.length}</strong><span>live quotes</span></div>
        </section>

        {error && <div className="error"><AlertTriangle size={17} />{error}</div>}
        {notice && <div className="notice"><Check size={17} />{notice}</div>}

        <section className="workspace-grid">
          <aside className="panel watchlist-sidebar">
            <div className="panel-head"><div><h3>Watchlists</h3><span>Saved to your account</span></div><button className="icon-button" aria-label="Create watchlist" onClick={() => setShowCreate(true)}><Plus size={17} /></button></div>
            {showCreate && <form className="inline-form" onSubmit={(event) => void handleCreate(event)}><input autoFocus value={newWatchlistName} onChange={(event) => setNewWatchlistName(event.target.value)} placeholder="Watchlist name" maxLength={80} /><button type="submit" disabled={action === "create"}>{action === "create" ? "…" : "Create"}</button><button type="button" className="icon-button" onClick={() => setShowCreate(false)}><X size={15} /></button></form>}
            {loadingWorkspace ? <div className="empty">Loading workspace…</div> : <div className="watchlist-list">
              {watchlists.map((watchlist) => <div key={watchlist.id} className={`watchlist-entry ${activeWatchlist?.id === watchlist.id ? "active" : ""}`}>
                {editingId === watchlist.id ? <div className="rename-form"><input autoFocus value={editingName} onChange={(event) => setEditingName(event.target.value)} maxLength={80} onKeyDown={(event) => { if (event.key === "Enter") void handleRename(watchlist.id); if (event.key === "Escape") setEditingId(null); }} /><button className="icon-button" onClick={() => void handleRename(watchlist.id)} disabled={action === `rename:${watchlist.id}`}><Check size={14} /></button></div> : <>
                  <button className="watchlist-select" onClick={() => setActiveWatchlistId(watchlist.id)}><Star size={15} fill={activeWatchlist?.id === watchlist.id ? "currentColor" : "none"} /><span>{watchlist.name}</span><small>{watchlist.watchlist_items.length}</small></button>
                  <div className="watchlist-actions"><button className="icon-button" aria-label={`Rename ${watchlist.name}`} onClick={() => { setEditingId(watchlist.id); setEditingName(watchlist.name); }}><Pencil size={13} /></button><button className="icon-button danger" aria-label={`Delete ${watchlist.name}`} onClick={() => void handleDelete(watchlist)} disabled={action === `delete:${watchlist.id}`}><Trash2 size={13} /></button></div>
                </>}
              </div>)}
            </div>}
          </aside>

          <section className="panel market-panel">
            <div className="panel-head workspace-head"><div><h3>{activeWatchlist?.name ?? "Watchlist"}</h3><span>{activeSymbols.length} symbols · automatic refresh every {refreshSeconds}s</span></div>{activeWatchlist && <div className="add-symbol"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter symbols" aria-label="Filter symbols" /><select value={symbolToAdd} onChange={(event) => setSymbolToAdd(event.target.value)} aria-label="Symbol to add">{availableSymbols.map((symbol) => <option key={symbol}>{symbol}</option>)}</select><button onClick={() => void handleAddSymbol()} disabled={Boolean(action) || activeSymbols.includes(symbolToAdd)}><Plus size={15} />Add</button></div>}</div>
            {!activeWatchlist ? <div className="empty">Create a watchlist to begin.</div> : activeSymbols.length === 0 ? <div className="empty"><Star size={22} /><strong>No symbols yet</strong><span>Add a symbol above to start monitoring this watchlist.</span></div> : <div className="quotes">
              {activeSymbols.map((symbol) => { const quote = quotes.find((item) => item.symbol === symbol); return <button key={symbol} className={`quote-row ${selected === symbol ? "selected" : ""}`} onClick={() => setSelected(symbol)}><div className="symbol">{symbol}</div><div className="price">{formatPrice(quote?.price ?? null)}</div><div className={`status ${statusClass(quote?.status ?? "UNAVAILABLE")}`}><span className="dot" />{quote?.status ?? "UNAVAILABLE"}</div><div className="timestamp">{quote?.timestamp ? formatTime(quote.timestamp) : "Unavailable"}</div><span className="row-remove" role="button" aria-label={`Remove ${symbol}`} onClick={(event) => { event.stopPropagation(); void handleRemoveSymbol(symbol); }}><X size={14} /></span></button>; })}
            </div>}
          </section>

          <div className="panel detail">
            <div className="panel-head"><div><h3>{selected ?? "Asset"}</h3><span>Canonical market snapshot</span></div><ShieldCheck size={20} /></div>
            {selectedQuote ? <><div className="big-price">{formatPrice(selectedQuote.price)}</div><div className={`large-status ${statusClass(selectedQuote.status)}`}><span className="dot" />{selectedQuote.status}</div><div className="metadata"><div><span>Provider</span><strong>{selectedQuote.source ?? "—"}</strong></div><div><span>Provider symbol</span><strong>{selectedQuote.provider_symbol}</strong></div><div><span>Updated</span><strong>{formatTime(selectedQuote.timestamp)}</strong></div><div><span>Latency</span><strong>{selectedQuote.latency_ms != null ? `${selectedQuote.latency_ms} ms` : "—"}</strong></div></div>{selectedQuote.error && <div className="warning"><AlertTriangle size={16} />{selectedQuote.error}</div>}<div className="eligibility"><Clock3 size={16} /><div><strong>{selectedQuote.status === "LIVE" ? "Research eligible" : "Research disabled"}</strong><span>{selectedQuote.status === "LIVE" ? "This quote passed the basic live-data validation gate." : "The system will not present this as a current market price."}</span></div></div></> : <div className="empty">Select an asset from the active watchlist.</div>}
          </div>
        </section>

        <footer>This tool provides market research and analysis assistance only. It is not financial advice, a recommendation to buy or sell, or a substitute for professional advice. Past performance is not indicative of future results. Users are solely responsible for their own decisions.</footer>
      </main>
    </div>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const handleAuthenticated = useCallback((nextUser: User) => { setSessionError(null); setUser(nextUser); }, []);
  const handleLogout = useCallback(() => setUser(null), []);

  useEffect(() => {
    let active = true;
    getCurrentUser().then((nextUser) => { if (active) setUser(nextUser); }).catch((err) => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 401) { setUser(null); return; }
      setSessionError(err instanceof Error ? err.message : "Unable to verify your session.");
    }).finally(() => { if (active) setCheckingSession(false); });
    return () => { active = false; };
  }, []);

  if (checkingSession) return <div className="auth-loading">Checking session…</div>;
  if (sessionError && !user) return <div className="auth-loading"><div className="error auth-error"><AlertTriangle size={17} />{sessionError}</div><button className="auth-submit" onClick={() => window.location.reload()}>Retry</button></div>;
  if (!user) return <AuthScreen onAuthenticated={handleAuthenticated} />;
  return <Dashboard user={user} onLogout={handleLogout} />;
}

export default App;
