import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Clock3, RefreshCw, ShieldCheck } from "lucide-react";
import { getQuotes, Quote } from "./api";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "NVDA", "AAPL", "SPY"];

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

function App() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState("BTC/USD");

  const refreshSeconds = Number(import.meta.env.VITE_QUOTE_REFRESH_SECONDS ?? 60);

  const loadQuotes = useCallback(async (force = false) => {
    try {
      setError(null);
      force ? setRefreshing(true) : setLoading(true);
      const next = await getQuotes(SYMBOLS, force);
      setQuotes(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to retrieve market data.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadQuotes(false);
    const timer = window.setInterval(() => void loadQuotes(false), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [loadQuotes, refreshSeconds]);

  const selectedQuote = useMemo(
    () => quotes.find((quote) => quote.symbol === selected),
    [quotes, selected],
  );

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <div className="eyebrow">Adaptive Intelligence</div>
          <h1>Market Research</h1>
        </div>
        <button className="refresh" onClick={() => void loadQuotes(true)} disabled={refreshing}>
          <RefreshCw size={16} className={refreshing ? "spin" : ""} />
          {refreshing ? "Refreshing" : "Refresh prices"}
        </button>
      </header>

      <main>
        <section className="hero">
          <div>
            <div className="eyebrow">Live market data</div>
            <h2>Research only what has passed data validation.</h2>
            <p>
              Prices are retrieved server-side from the configured market-data provider.
              The interface never substitutes hardcoded demo values for unavailable live data.
            </p>
          </div>
          <div className="hero-stat">
            <Activity size={20} />
            <strong>{quotes.filter((q) => q.status === "LIVE").length}/{SYMBOLS.length}</strong>
            <span>live quotes</span>
          </div>
        </section>

        {error && <div className="error"><AlertTriangle size={17} />{error}</div>}

        <section className="grid">
          <div className="panel">
            <div className="panel-head">
              <div>
                <h3>Market scanner</h3>
                <span>Automatic refresh every {refreshSeconds}s</span>
              </div>
            </div>

            {loading ? (
              <div className="empty">Loading live quotes…</div>
            ) : (
              <div className="quotes">
                {quotes.map((quote) => (
                  <button
                    key={quote.symbol}
                    className={`quote-row ${selected === quote.symbol ? "selected" : ""}`}
                    onClick={() => setSelected(quote.symbol)}
                  >
                    <div className="symbol">{quote.symbol}</div>
                    <div className="price">{formatPrice(quote.price)}</div>
                    <div className={`status ${statusClass(quote.status)}`}>
                      <span className="dot" />
                      {quote.status}
                    </div>
                    <div className="timestamp">
                      {quote.timestamp ? formatTime(quote.timestamp) : "Unavailable"}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="panel detail">
            <div className="panel-head">
              <div>
                <h3>{selected}</h3>
                <span>Canonical market snapshot</span>
              </div>
              <ShieldCheck size={20} />
            </div>

            {selectedQuote ? (
              <>
                <div className="big-price">{formatPrice(selectedQuote.price)}</div>
                <div className={`large-status ${statusClass(selectedQuote.status)}`}>
                  <span className="dot" />
                  {selectedQuote.status}
                </div>

                <div className="metadata">
                  <div><span>Provider</span><strong>{selectedQuote.source ?? "—"}</strong></div>
                  <div><span>Provider symbol</span><strong>{selectedQuote.provider_symbol}</strong></div>
                  <div><span>Updated</span><strong>{formatTime(selectedQuote.timestamp)}</strong></div>
                  <div><span>Latency</span><strong>{selectedQuote.latency_ms != null ? `${selectedQuote.latency_ms} ms` : "—"}</strong></div>
                </div>

                {selectedQuote.error && (
                  <div className="warning">
                    <AlertTriangle size={16} />
                    {selectedQuote.error}
                  </div>
                )}

                <div className="eligibility">
                  <Clock3 size={16} />
                  <div>
                    <strong>
                      {selectedQuote.status === "LIVE"
                        ? "Research eligible"
                        : "Research disabled"}
                    </strong>
                    <span>
                      {selectedQuote.status === "LIVE"
                        ? "This quote passed the basic live-data validation gate."
                        : "The system will not score or present this as a current market price."}
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <div className="empty">Select an asset.</div>
            )}
          </div>
        </section>

        <footer>
          This tool provides market research and analysis assistance only. It is not financial
          advice, a recommendation to buy or sell, or a substitute for professional advice.
          Trading and investing involve substantial risk of loss. Past performance is not
          indicative of future results. Users are solely responsible for their own decisions.
        </footer>
      </main>
    </div>
  );
}

export default App;
