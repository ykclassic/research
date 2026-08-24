import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, Clock3, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import {
  ApiError,
  confirmPasswordReset,
  getCurrentUser,
  getQuotes,
  login,
  logout,
  Quote,
  register,
  requestPasswordReset,
  User,
} from "./api";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "NVDA", "AAPL", "SPY"];
type AuthMode = "login" | "register" | "forgot" | "reset";

function formatPrice(price: number | null): string {
  if (price === null) return "—";
  if (price >= 1000) return price.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (price >= 1) return price.toLocaleString(undefined, { maximumFractionDigits: 5 });
  return price.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function formatTime(timestamp: string | null): string {
  if (!timestamp) return "No timestamp";
  return new Date(timestamp).toLocaleTimeString();
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

  const clearRecoveryUrl = () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  };

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

  const title =
    mode === "login"
      ? "Welcome back"
      : mode === "register"
        ? "Create your account"
        : mode === "forgot"
          ? "Reset your password"
          : "Choose a new password";

  const subtitle =
    mode === "login"
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
        {error && (
          <div className="error auth-error" role="alert">
            <AlertTriangle size={17} />
            {error}
          </div>
        )}
        <form onSubmit={submit} className="auth-form">
          {(mode === "login" || mode === "register" || mode === "forgot") && (
            <label>
              Email
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
          )}
          {(mode === "login" || mode === "register" || mode === "reset") && (
            <label>
              Password
              <input
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={8}
                required
              />
            </label>
          )}
          {(mode === "register" || mode === "reset") && (
            <label>
              Confirm password
              <input
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                minLength={8}
                required
              />
            </label>
          )}
          <button className="auth-submit" type="submit" disabled={busy}>
            {busy
              ? "Please wait…"
              : mode === "login"
                ? "Sign in"
                : mode === "register"
                  ? "Register"
                  : mode === "forgot"
                    ? "Send reset link"
                    : "Update password"}
          </button>
        </form>

        {mode === "login" && (
          <button className="auth-switch" type="button" onClick={() => switchMode("forgot")}>
            Forgot your password?
          </button>
        )}
        {mode === "login" && (
          <button className="auth-switch" type="button" onClick={() => switchMode("register")}>
            Need an account? Register
          </button>
        )}
        {mode === "register" && (
          <button className="auth-switch" type="button" onClick={() => switchMode("login")}>
            Already registered? Sign in
          </button>
        )}
        {mode === "forgot" && (
          <button className="auth-switch" type="button" onClick={() => switchMode("login")}>
            Back to Sign in
          </button>
        )}
        {mode === "reset" && (
          <button className="auth-switch" type="button" onClick={() => { clearRecoveryUrl(); switchMode("login"); }}>
            Back to Sign in
          </button>
        )}
      </div>
    </div>
  );
}

function Dashboard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState("BTC/USD");
  const requestInFlight = useRef(false);
  const refreshSecondsRaw = Number(import.meta.env.VITE_QUOTE_REFRESH_SECONDS ?? 60);
  const refreshSeconds = Number.isFinite(refreshSecondsRaw) && refreshSecondsRaw >= 10 ? refreshSecondsRaw : 60;

  const loadQuotes = useCallback(async (force = false) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      setError(null);
      if (force) setRefreshing(true);
      else if (quotes.length === 0) setLoading(true);
      const nextQuotes = await getQuotes(SYMBOLS, force);
      setQuotes(nextQuotes);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "Unable to retrieve market data.");
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, [onLogout, quotes.length]);

  useEffect(() => {
    void loadQuotes(false);
    const timer = window.setInterval(() => void loadQuotes(false), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [loadQuotes, refreshSeconds]);

  const selectedQuote = useMemo(() => quotes.find((quote) => quote.symbol === selected), [quotes, selected]);

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
          <button className="refresh" onClick={() => void loadQuotes(true)} disabled={refreshing}>
            <RefreshCw size={16} className={refreshing ? "spin" : ""} />{refreshing ? "Refreshing" : "Refresh prices"}
          </button>
        </div>
      </header>
      <main>
        <section className="hero">
          <div>
            <div className="eyebrow">Live market data</div>
            <h2>Research only what has passed data validation.</h2>
            <p>Prices are retrieved server-side from the configured market-data provider. The interface never substitutes hardcoded demo values for unavailable live data.</p>
          </div>
          <div className="hero-stat"><Activity size={20} /><strong>{quotes.filter((q) => q.status === "LIVE").length}/{SYMBOLS.length}</strong><span>live quotes</span></div>
        </section>
        {error && <div className="error"><AlertTriangle size={17} />{error}</div>}
        <section className="grid">
          <div className="panel">
            <div className="panel-head"><div><h3>Market scanner</h3><span>Automatic refresh every {refreshSeconds}s</span></div></div>
            {loading ? <div className="empty">Loading live quotes…</div> : (
              <div className="quotes">
                {quotes.map((quote) => (
                  <button key={quote.symbol} className={`quote-row ${selected === quote.symbol ? "selected" : ""}`} onClick={() => setSelected(quote.symbol)}>
                    <div className="symbol">{quote.symbol}</div><div className="price">{formatPrice(quote.price)}</div>
                    <div className={`status ${statusClass(quote.status)}`}><span className="dot" />{quote.status}</div>
                    <div className="timestamp">{quote.timestamp ? formatTime(quote.timestamp) : "Unavailable"}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="panel detail">
            <div className="panel-head"><div><h3>{selected}</h3><span>Canonical market snapshot</span></div><ShieldCheck size={20} /></div>
            {selectedQuote ? (
              <>
                <div className="big-price">{formatPrice(selectedQuote.price)}</div>
                <div className={`large-status ${statusClass(selectedQuote.status)}`}><span className="dot" />{selectedQuote.status}</div>
                <div className="metadata">
                  <div><span>Provider</span><strong>{selectedQuote.source ?? "—"}</strong></div>
                  <div><span>Provider symbol</span><strong>{selectedQuote.provider_symbol}</strong></div>
                  <div><span>Updated</span><strong>{formatTime(selectedQuote.timestamp)}</strong></div>
                  <div><span>Latency</span><strong>{selectedQuote.latency_ms != null ? `${selectedQuote.latency_ms} ms` : "—"}</strong></div>
                </div>
                {selectedQuote.error && <div className="warning"><AlertTriangle size={16} />{selectedQuote.error}</div>}
                <div className="eligibility">
                  <Clock3 size={16} />
                  <div>
                    <strong>{selectedQuote.status === "LIVE" ? "Research eligible" : "Research disabled"}</strong>
                    <span>{selectedQuote.status === "LIVE" ? "This quote passed the basic live-data validation gate." : "The system will not score or present this as a current market price."}</span>
                  </div>
                </div>
              </>
            ) : <div className="empty">Select an asset.</div>}
          </div>
        </section>
        <footer>This tool provides market research and analysis assistance only. It is not financial advice, a recommendation to buy or sell, or a substitute for professional advice. Trading and investing involve substantial risk of loss. Past performance is not indicative of future results. Users are solely responsible for their own decisions.</footer>
      </main>
    </div>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const handleAuthenticated = useCallback((nextUser: User) => {
    setSessionError(null);
    setUser(nextUser);
  }, []);

  const handleLogout = useCallback(() => {
    setUser(null);
  }, []);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((nextUser) => {
        if (active) setUser(nextUser);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          setUser(null);
          return;
        }
        setSessionError(err instanceof Error ? err.message : "Unable to verify your session.");
      })
      .finally(() => {
        if (active) setCheckingSession(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (checkingSession) return <div className="auth-loading">Checking session…</div>;
  if (sessionError && !user) {
    return (
      <div className="auth-loading">
        <div className="error auth-error"><AlertTriangle size={17} />{sessionError}</div>
        <button className="auth-submit" onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }
  if (!user) return <AuthScreen onAuthenticated={handleAuthenticated} />;
  return <Dashboard user={user} onLogout={handleLogout} />;
}

export default App;
