"use client";

import { useEffect, useMemo, useState } from "react";

type Candle = { t: number; o: number; h: number; l: number; c: number; v: number };

const API = "http://localhost:8000";

export default function HomePage() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbol, setSymbol] = useState<string>("BTCUSDT");
  const [selected, setSelected] = useState<Set<string>>(new Set(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]));
  const [candles, setCandles] = useState<Candle[]>([]);

  const [strategy, setStrategy] = useState<string>("ema_cross");
  const [params, setParams] = useState<Record<string, string>>({ fast: "7", slow: "18", stop_lookback: "11", rr: "3", ma_type: "ema", direction: "both", trend_enabled: "1", trend_interval: "15m", trend_ma_type: "ema", trend_period: "200" });
  const [stats, setStats] = useState<any>(null);
  const [batchResults, setBatchResults] = useState<any>(null);
  const [runningBatch, setRunningBatch] = useState<boolean>(false);

  const [liveState, setLiveState] = useState<any>(null);
  const [livePolling, setLivePolling] = useState<boolean>(false);

  useEffect(() => {
    fetch(`${API}/api/symbols`).then(r => r.json()).then(d => setSymbols(d.symbols));
  }, []);

  useEffect(() => {
    fetch(`${API}/api/candles?symbol=${encodeURIComponent(symbol)}&interval=3m&limit=300`)
      .then(r => r.json())
      .then(d => setCandles(d.candles));
  }, [symbol]);

  const last = useMemo(() => candles[candles.length - 1], [candles]);

  function buildParams() {
    return Object.fromEntries(
      Object.entries(params).map(([k, v]) => {
        if (k === "trend_interval") return [k, v];
        if (k === "ma_type") return [k, v];
        if (k === "direction") return [k, v];
        if (k === "trend_ma_type") return [k, v];
        if (k === "trend_enabled") return [k, v === "1" || v.toLowerCase() === "true"];
        return [k, Number(v)];
      })
    );
  }

  async function runBacktest() {
    const payload = {
      symbol,
      interval: "3m",
      days: 30,
      max_candles: 20000,
      strategy,
      params: buildParams(),
      initial_cash: 1000,
      fee_bps: 10,
      slippage_bps: 2,
    };

    const res = await fetch(`${API}/api/backtest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    setStats(data.stats ?? data);
  }

  async function runBatchBacktest() {
    const payload = {
      symbols: Array.from(selected),
      backtest: {
        symbol: "BTCUSDT",
        interval: "3m",
        days: 30,
        max_candles: 20000,
        strategy,
        params: buildParams(),
        initial_cash: 1000,
        fee_bps: 10,
        slippage_bps: 2,
      },
    };

    setRunningBatch(true);
    setBatchResults(null);
    try {
      const res = await fetch(`${API}/api/backtest/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      setBatchResults(data);
    } finally {
      setRunningBatch(false);
    }
  }

  async function fetchLive() {
    try {
      const res = await fetch(`${API}/api/live/state`);
      const data = await res.json();
      setLiveState(data);
    } catch (e: any) {
      setLiveState({ running: false, last_error: String(e?.message ?? e), markets: {} });
      throw e;
    }
  }

  async function startLive() {
    const payload = {
      symbols: Array.from(selected),
      strategy,
      params: buildParams(),
      trade_mode: "off",
    };
    await fetch(`${API}/api/live/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    try {
      await fetchLive();
      setLivePolling(true);
    } catch {
      setLivePolling(false);
    }
  }

  async function stopLive() {
    await fetch(`${API}/api/live/stop`, { method: "POST" });
    try {
      await fetchLive();
    } catch {
      // ignore
    }
    setLivePolling(false);
  }

  useEffect(() => {
    fetchLive().catch(() => {});
  }, []);

  useEffect(() => {
    if (!livePolling) return;
    const id = setInterval(() => {
      fetchLive().catch(() => {});
    }, 2000);
    return () => clearInterval(id);
  }, [livePolling]);

  return (
    <main style={{ padding: 16, maxWidth: 980, margin: "0 auto" }}>
      <h1 style={{ marginTop: 0 }}>Crypto Paper (MVP)</h1>

      <section style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <label>
          Symbol:{" "}
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {(symbols.length ? symbols : ["BTCUSDT"]).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        <details>
          <summary style={{ cursor: "pointer" }}>Batch markets ({selected.size})</summary>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8, paddingTop: 8, maxWidth: 640 }}>
            {(symbols.length ? symbols : ["BTCUSDT"]).map((s) => (
              <label key={s} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={selected.has(s)}
                  onChange={(e) => {
                    setSelected((prev) => {
                      const next = new Set(prev);
                      if (e.target.checked) next.add(s);
                      else next.delete(s);
                      return next;
                    });
                  }}
                />
                {s}
              </label>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, paddingTop: 8 }}>
            <button
              onClick={() => setSelected(new Set(symbols))}
              disabled={!symbols.length}
              type="button"
            >
              Select all
            </button>
            <button onClick={() => setSelected(new Set())} type="button">Clear</button>
          </div>
        </details>

        <label>
          Strategy:{" "}
          <select
            value={strategy}
            onChange={(e) => {
              const v = e.target.value;
              setStrategy(v);
              setParams(
                v === "ema_cross"
                  ? { fast: "7", slow: "18", stop_lookback: "11", rr: "3", ma_type: "ema", direction: "both", trend_enabled: "1", trend_interval: "15m", trend_ma_type: "ema", trend_period: "200" }
                  : { period: "14", buy_below: "30", sell_above: "70", stop_lookback: "11", rr: "3", direction: "both", trend_enabled: "1", trend_interval: "15m", trend_ma_type: "ema", trend_period: "200" }
              );
            }}
          >
            <option value="ema_cross">EMA/SMA cross</option>
            <option value="rsi_mean_reversion">RSI mean reversion</option>
          </select>
        </label>

        <label>
          Direction:{" "}
          <select value={params.direction ?? "both"} onChange={(e) => setParams((p) => ({ ...p, direction: e.target.value }))}>
            <option value="both">Both</option>
            <option value="long">Long only</option>
            <option value="short">Short only</option>
          </select>
        </label>

        {Object.entries(params).map(([k, v]) => (
          <label key={k}>
            {k}:{" "}
            <input
              value={v}
              onChange={(e) => setParams((p) => ({ ...p, [k]: e.target.value }))}
              style={{ width: 90 }}
            />
          </label>
        ))}

        <button onClick={runBacktest}>Run backtest</button>
        <button onClick={runBatchBacktest} disabled={runningBatch || selected.size === 0}>
          {runningBatch ? "Running batch…" : `Run batch (${selected.size})`}
        </button>
      </section>

      <section style={{ marginTop: 16 }}>
        <h2>Live screener (Binance candles)</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button onClick={fetchLive}>Refresh</button>
          {!liveState?.running ? (
            <button onClick={startLive} disabled={selected.size === 0}>Start live screener</button>
          ) : (
            <button onClick={stopLive}>Stop live screener</button>
          )}
          <span style={{ color: "#666" }}>
            {liveState?.running ? "running" : "stopped"}
            {liveState?.last_error ? ` — error: ${liveState.last_error}` : ""}
          </span>
        </div>

        {liveState?.markets ? (
          <div style={{ marginTop: 8, overflowX: "auto" }}>
            <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%", minWidth: 700 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                  <th>Symbol</th>
                  <th>Last</th>
                  <th>Trend MA</th>
                  <th>Signal</th>
                  <th>Stop</th>
                  <th>TP</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(liveState.markets).map((m: any) => (
                  <tr key={m.symbol} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{m.symbol}</td>
                    <td>{m.last_price?.toFixed ? m.last_price.toFixed(2) : "—"}</td>
                    <td>{m.trend_ma?.toFixed ? m.trend_ma.toFixed(2) : "—"}</td>
                    <td style={{ fontWeight: 600 }}>{m.signal ?? "—"}</td>
                    <td>{m.signal_meta?.stop ? Number(m.signal_meta.stop).toFixed(2) : "—"}</td>
                    <td>{m.signal_meta?.tp ? Number(m.signal_meta.tp).toFixed(2) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: "#666" }}>No live state yet.</p>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <h2>Latest candle (3m)</h2>
        {last ? (
          <pre style={{ background: "#f6f6f6", padding: 12, overflowX: "auto" }}>{JSON.stringify(last, null, 2)}</pre>
        ) : (
          <p>Loading candles…</p>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <h2>Backtest stats</h2>
        {stats ? (
          <pre style={{ background: "#f6f6f6", padding: 12, overflowX: "auto" }}>{JSON.stringify(stats, null, 2)}</pre>
        ) : (
          <p>Run a backtest to see results.</p>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <h2>Batch results</h2>
        {batchResults?.results ? (
          <>
            {(() => {
              const rows = batchResults.results as any[];
              return (
                <div style={{ overflowX: "auto" }}>
                  <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%", minWidth: 640 }}>
                    <thead>
                      <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                        <th>Symbol</th>
                        <th>Return %</th>
                        <th>Trades</th>
                        <th>Start equity</th>
                        <th>End equity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r: any) => {
                        const s = r.stats ?? {};
                        const ret = typeof s.return_pct === "number" ? s.return_pct : null;
                        return (
                          <tr key={r.symbol} style={{ borderBottom: "1px solid #f0f0f0" }}>
                            <td style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{r.symbol}</td>
                            <td style={{ color: ret === null ? undefined : ret >= 0 ? "#0a7" : "#c22" }}>
                              {ret === null ? "—" : ret.toFixed(2)}
                            </td>
                            <td>{s.trades ?? "—"}</td>
                            <td>{s.start_equity?.toFixed ? s.start_equity.toFixed(2) : "—"}</td>
                            <td>{s.end_equity?.toFixed ? s.end_equity.toFixed(2) : "—"}</td>
                          </tr>
                        );
                      })}
                      <tr style={{ borderTop: "2px solid #ddd", fontWeight: 600 }}>
                        <td colSpan={4}>Batch total change</td>
                        <td>
                          {(() => {
                            const starts = rows.map((r) => r?.stats?.start_equity).filter((x) => typeof x === "number") as number[];
                            const ends = rows.map((r) => r?.stats?.end_equity).filter((x) => typeof x === "number") as number[];
                            if (!starts.length || !ends.length || starts.length !== ends.length) return "—";
                            const totalStart = starts.reduce((a, b) => a + b, 0);
                            const totalEnd = ends.reduce((a, b) => a + b, 0);
                            const delta = totalEnd - totalStart;
                            const pct = totalStart ? (delta / totalStart) * 100 : NaN;
                            const sign = delta >= 0 ? "+" : "";
                            return `${sign}$${delta.toFixed(2)} (${pct.toFixed(2)}%)`;
                          })()}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              );
            })()}

            <details style={{ marginTop: 8 }}>
              <summary style={{ cursor: "pointer" }}>Raw JSON</summary>
              <pre style={{ background: "#f6f6f6", padding: 12, overflowX: "auto" }}>{JSON.stringify(batchResults, null, 2)}</pre>
            </details>
          </>
        ) : (
          <p>Run a batch backtest to compare multiple markets.</p>
        )}
      </section>

      <footer style={{ marginTop: 24, color: "#666" }}>
        <small>Not financial advice. Paper/backtest only.</small>
      </footer>
    </main>
  );
}
