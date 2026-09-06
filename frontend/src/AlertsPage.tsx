import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, BellRing, Check, Pause, Play, Plus, Trash2, X } from "lucide-react";
import { AlertChannel, AlertCondition, AlertEvent, AlertRule, createAlertRule, deleteAlertRule, evaluateAlerts, getAlertEvents, getAlertRules, markAlertRead, updateAlertRule } from "./alertsApi";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD", "USD/JPY", "NVDA", "AAPL", "MSFT", "SPY"];
const CONDITION_LABELS: Record<AlertCondition, string> = { RSI_THRESHOLD: "RSI threshold", PRICE_CROSS: "Price crosses", REGIME_CHANGE: "Regime changes", BULLISH_BOS: "Bullish BOS detected" };

function describe(rule: AlertRule): string {
  if (rule.condition_type === "RSI_THRESHOLD") return `RSI(14) ${({ LT: "<", LTE: "≤", GT: ">", GTE: "≥" } as Record<string, string>)[rule.operator || "LT"]} ${rule.threshold}`;
  if (rule.condition_type === "PRICE_CROSS") return `Price crosses ${rule.operator === "ABOVE" ? "above" : "below"} ${Number(rule.threshold).toLocaleString()}`;
  if (rule.condition_type === "REGIME_CHANGE") return "Any confirmed regime transition";
  return "A new bullish break of structure is detected";
}

function formatTime(value: string): string { return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }

export default function AlertsPage({ onClose }: { onClose?: () => void }) {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [symbol, setSymbol] = useState("BTC/USD");
  const [condition, setCondition] = useState<AlertCondition>("RSI_THRESHOLD");
  const [operator, setOperator] = useState("LT");
  const [threshold, setThreshold] = useState("30");
  const [cooldown, setCooldown] = useState("60");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [permission, setPermission] = useState<NotificationPermission>(typeof Notification === "undefined" ? "denied" : Notification.permission);

  const refresh = useCallback(async () => {
    try { setRules(await getAlertRules()); setEvents(await getAlertEvents()); setError(""); } catch (err) { setError(err instanceof Error ? err.message : "Unable to load alerts."); }
  }, []);

  const checkNow = useCallback(async (notify = true) => {
    try {
      const created = await evaluateAlerts();
      if (created.length) {
        setEvents(current => [...created, ...current.filter(item => !created.some(next => next.id === item.id))].slice(0, 50));
        if (notify && typeof Notification !== "undefined" && Notification.permission === "granted") created.forEach(event => new Notification(event.title, { body: event.message }));
      }
      setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Alert monitoring check failed."); }
  }, []);

  useEffect(() => { void refresh(); const timer = window.setInterval(() => { void checkNow(); }, 60_000); return () => window.clearInterval(timer); }, [refresh, checkNow]);

  const requestNotifications = async () => { if (typeof Notification === "undefined") return; const result = await Notification.requestPermission(); setPermission(result); };

  const addRule = async () => {
    setBusy(true); setError("");
    try {
      await createAlertRule({ symbol, condition_type: condition, operator: condition === "RSI_THRESHOLD" || condition === "PRICE_CROSS" ? operator : undefined, threshold: condition === "RSI_THRESHOLD" || condition === "PRICE_CROSS" ? Number(threshold) : undefined, timeframe: "1h", cooldown_minutes: Number(cooldown), channels: ["WEB"] });
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to create alert."); } finally { setBusy(false); }
  };

  const unread = useMemo(() => events.filter(event => !event.read_at).length, [events]);
  const setConditionAndDefaults = (next: AlertCondition) => { setCondition(next); if (next === "RSI_THRESHOLD") { setOperator("LT"); setThreshold("30"); } else if (next === "PRICE_CROSS") { setOperator("ABOVE"); setThreshold("110000"); } };

  return <section className="alerts-page">
    <div className="alerts-header"><div><div className="eyebrow">Monitoring</div><h1>Alerts & Monitoring</h1><p>Create deterministic market alerts and receive web notifications without turning alerts into trade execution.</p></div><div className="alerts-header-actions"><button type="button" className="secondary-button" onClick={requestNotifications} disabled={permission === "granted"}><BellRing size={16} /> {permission === "granted" ? "Web notifications on" : "Enable web notifications"}</button>{onClose && <button type="button" className="icon-button" onClick={onClose} aria-label="Close alerts"><X size={20} /></button>}</div></div>
    <div className="alerts-grid">
      <div className="alerts-main">
        <div className="alert-card create-alert-card"><div className="card-heading"><div><span className="section-kicker">Create rule</span><h2>Alert me when…</h2></div><Bell size={18} /></div>
          <div className="alert-form-grid"><label>Asset<select value={symbol} onChange={event => setSymbol(event.target.value)}>{SYMBOLS.map(item => <option key={item}>{item}</option>)}</select></label><label>Condition<select value={condition} onChange={event => setConditionAndDefaults(event.target.value as AlertCondition)}>{Object.entries(CONDITION_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          {condition === "RSI_THRESHOLD" && <><label>Operator<select value={operator} onChange={event => setOperator(event.target.value)}><option value="LT">RSI &lt; threshold</option><option value="LTE">RSI ≤ threshold</option><option value="GT">RSI &gt; threshold</option><option value="GTE">RSI ≥ threshold</option></select></label><label>RSI threshold<input type="number" min="0" max="100" value={threshold} onChange={event => setThreshold(event.target.value)} /></label></>}
          {condition === "PRICE_CROSS" && <><label>Direction<select value={operator} onChange={event => setOperator(event.target.value)}><option value="ABOVE">Crosses above</option><option value="BELOW">Crosses below</option></select></label><label>Price level<input type="number" min="0" step="any" value={threshold} onChange={event => setThreshold(event.target.value)} /></label></>}
          <label>Cooldown (minutes)<input type="number" min="0" max="10080" value={cooldown} onChange={event => setCooldown(event.target.value)} /></label></div>
          <div className="alert-rule-preview"><strong>{symbol}</strong><span>{describe({ symbol, condition_type: condition, operator, threshold: Number(threshold), timeframe: "1h" } as AlertRule)}</span><small>Evaluated on completed 1h market data · web channel</small></div>
          <button type="button" className="primary-button" onClick={() => void addRule()} disabled={busy}><Plus size={16} /> {busy ? "Creating…" : "Create alert"}</button>
        </div>
        <div className="alert-card"><div className="card-heading"><div><span className="section-kicker">Active rules</span><h2>Your alerts</h2></div><span className="count-pill">{rules.length}</span></div>{rules.length === 0 ? <div className="empty-state">No alerts yet. Create your first rule above.</div> : <div className="rules-list">{rules.map(rule => <div className={`rule-row ${rule.enabled ? "" : "disabled"}`} key={rule.id}><div className="rule-icon"><Bell size={16} /></div><div className="rule-copy"><strong>{rule.symbol}</strong><span>{describe(rule)}</span><small>{rule.timeframe} · cooldown {rule.cooldown_minutes}m · {rule.channels.join(", ")}</small></div><div className="rule-actions"><button type="button" className="icon-button" onClick={() => void updateAlertRule(rule.id, { enabled: !rule.enabled }).then(refresh)} aria-label={rule.enabled ? "Pause alert" : "Enable alert"}>{rule.enabled ? <Pause size={16} /> : <Play size={16} />}</button><button type="button" className="icon-button danger" onClick={() => void deleteAlertRule(rule.id).then(refresh)} aria-label="Delete alert"><Trash2 size={16} /></button></div></div>)}</div>}</div>
      </div>
      <aside className="alerts-side"><div className="alert-card"><div className="card-heading"><div><span className="section-kicker">Activity</span><h2>Notifications {unread > 0 && <span className="unread-badge">{unread}</span>}</h2></div><button type="button" className="text-button" onClick={() => void checkNow(false)}>Check now</button></div>{events.length === 0 ? <div className="empty-state">Triggered alerts will appear here.</div> : <div className="events-list">{events.slice(0, 20).map(event => <div className={`event-row ${event.read_at ? "read" : "unread"}`} key={event.id}><div className="event-dot" /><div><strong>{event.title}</strong><p>{event.message}</p><small>{formatTime(event.triggered_at)}</small>{!event.read_at && <button type="button" className="read-button" onClick={() => void markAlertRead(event.id).then(updated => setEvents(current => current.map(item => item.id === updated.id ? updated : item)))}><Check size={13} /> Mark read</button>}</div></div>)}</div>}</div><div className="monitoring-note"><strong>Safe by design</strong><p>Alerts observe market conditions only. They do not create signals, authorize trades, or execute orders.</p><div><span>WEB</span><span>EMAIL · planned</span><span>DISCORD · planned</span></div></div></aside>
    </div>{error && <div className="alerts-error" role="alert">{error}</div>}
  </section>;
}
