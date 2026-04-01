"use client";

import { useEffect, useMemo, useState } from "react";

type Candle = { t: number; o: number; h: number; l: number; c: number; v: number };

const API = "http://localhost:8000";

export default function HomePage() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbol, setSymbol] = useState<string>("XBT/USD");
  const [selected, setSelected] = useState<Set<string>>(new Set(["XBT/USD", "ETH/USD", "SOL/USD", "XRP/USD"]));

  // Candle interval to monitor (default 5m so we're Kraken-compatible)
  const [baseInterval, setBaseInterval] = useState<string>("5m");

  const [candles, setCandles] = useState<Candle[]>([]);

  const [strategy, setStrategy] = useState<string>("ema_cross");
  const [params, setParams] = useState<Record<string, string>>({ fast: "7", slow: "18", stop_lookback: "11", rr: "3", ma_type: "ema", direction: "both", trend_enabled: "1", trend_interval: "15m", trend_ma_type: "ema", trend_period: "200" });
  const [stats, setStats] = useState<any>(null);
  const [batchResults, setBatchResults] = useState<any>(null);
  const [runningBatch, setRunningBatch] = useState<boolean>(false);

  const [liveState, setLiveState] = useState<any>(null);
  const [livePolling, setLivePolling] = useState<boolean>(false);
  const [tradeMode, setTradeMode] = useState<string>("off");
  const [tradingEnabled, setTradingEnabled] = useState<boolean>(false);
  const [execLogs, setExecLogs] = useState<any[]>([]);
  const [paperTrades, setPaperTrades] = useState<any>(null);
  const [openPositions, setOpenPositions] = useState<any[]>([]);

  useEffect(() => {
    fetch(`${API}/api/symbols`).then(r => r.json()).then(d => setSymbols(d.symbols));
  }, []);

  useEffect(() => {
    fetch(`${API}/api/candles?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(baseInterval)}&limit=300`)
      .then(r => r.json())
      .then(d => setCandles(d.candles));
  }, [symbol, baseInterval]);

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
      interval: baseInterval,
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
        interval: baseInterval,
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
      if (data.config?.trade_mode) {
        setTradeMode(data.config.trade_mode);
      }
    } catch (e: any) {
      setLiveState({ running: false, last_error: String(e?.message ?? e), markets: {} });
      throw e;
    }
  }

  async function fetchTradeEnabled() {
    try {
      const res = await fetch(`${API}/api/live/trade-enabled`);
      const data = await res.json();
      setTradingEnabled(data.enabled);
      if (data.current_mode) setTradeMode(data.current_mode);
    } catch {
      setTradingEnabled(false);
    }
  }

  async function fetchLogs() {
    try {
      const res = await fetch(`${API}/api/live/logs?limit=50`);
      const data = await res.json();
      setExecLogs(data.logs || []);
    } catch {
      // ignore
    }
  }

  async function fetchPaperTrades() {
    try {
      const [tradesRes, posRes] = await Promise.all([
        fetch(`${API}/api/live/paper-trades?limit=20`),
        fetch(`${API}/api/live/open-positions`),
      ]);
      const tradesData = await tradesRes.json();
      const posData = await posRes.json();
      setPaperTrades(tradesData);
      setOpenPositions(posData.positions || []);
    } catch {
      // ignore
    }
  }

  async function setTradeModeApi(mode: string) {
    try {
      const res = await fetch(`${API}/api/live/trade-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      const data = await res.json();
      if (data.ok) {
        setTradeMode(data.mode);
      } else {
        alert(data.error || "Failed to set trade mode");
      }
    } catch (e: any) {
      alert("Error: " + (e?.message ?? e));
    }
  }

  async function startLive() {
    const trendInterval = String(params.trend_interval ?? "15m");
    const payload = {
      symbols: Array.from(selected),
      base_interval: baseInterval,
      trend_interval: trendInterval,
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
    fetchTradeEnabled();
  }, []);

  useEffect(() => {
    if (!livePolling) return;
    const id = setInterval(() => {
      fetchLive().catch(() => {});
      fetchLogs();
      if (tradeMode === "paper") {
        fetchPaperTrades();
      }
    }, 2000);
    return () => clearInterval(id);
  }, [livePolling, tradeMode]);

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

        <label>
          Interval:{" "}
          <select value={baseInterval} onChange={(e) => setBaseInterval(e.target.value)}>
            <option value="1m">1m</option>
            <option value="5m">5m</option>
            <option value="15m">15m</option>
            <option value="30m">30m</option>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
            <option value="1d">1d</option>
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

        {/* Trade mode controls */}
        <div style={{ marginTop: 12, padding: 12, background: tradeMode === "live_kraken" ? "#fff3cd" : "#f6f6f6", borderRadius: 6 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <strong>Trade Mode:</strong>
            <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <input
                type="radio"
                name="tradeMode"
                checked={tradeMode === "off"}
                onChange={() => setTradeModeApi("off")}
              />
              Off (signals only)
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <input
                type="radio"
                name="tradeMode"
                checked={tradeMode === "paper"}
                onChange={() => setTradeModeApi("paper")}
              />
              Paper trading
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 4, color: tradingEnabled ? undefined : "#999" }}>
              <input
                type="radio"
                name="tradeMode"
                checked={tradeMode === "live_kraken"}
                onChange={() => setTradeModeApi("live_kraken")}
                disabled={!tradingEnabled}
              />
              🔴 Live Kraken
              {!tradingEnabled && <span style={{ fontSize: 12 }}>(disabled)</span>}
            </label>
          </div>
          {tradeMode === "live_kraken" && (
            <div style={{ marginTop: 8, color: "#856404", fontWeight: 500 }}>
              ⚠️ LIVE TRADING ENABLED — Real orders will be placed on Kraken
            </div>
          )}
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

        {/* Execution logs */}
        {(tradeMode !== "off" || execLogs.length > 0) && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>Execution Logs</h3>
              <button onClick={fetchLogs} style={{ fontSize: 12 }}>Refresh logs</button>
            </div>
            <div
              style={{
                marginTop: 8,
                maxHeight: 200,
                overflowY: "auto",
                background: "#1a1a1a",
                color: "#f0f0f0",
                padding: 12,
                borderRadius: 6,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: 12,
              }}
            >
              {execLogs.length === 0 ? (
                <div style={{ color: "#666" }}>No execution logs yet.</div>
              ) : (
                execLogs.map((log, i) => {
                  const time = new Date(log.ts_ms).toLocaleTimeString();
                  const levelColor = log.level === "error" ? "#f44" : log.level === "warn" ? "#fa0" : "#0f0";
                  return (
                    <div key={i} style={{ marginBottom: 4 }}>
                      <span style={{ color: "#888" }}>[{time}]</span>{" "}
                      <span style={{ color: levelColor }}>[{log.level.toUpperCase()}]</span>{" "}
                      {log.message}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* Paper trading positions and trades */}
        {tradeMode === "paper" && (
          <div style={{ marginTop: 16 }}>
            {/* Open positions */}
            {openPositions.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <h3 style={{ margin: "0 0 8px 0" }}>📊 Open Positions</h3>
                <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Entry</th>
                      <th>Current</th>
                      <th>Stop</th>
                      <th>TP</th>
                      <th>Unrealized P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {openPositions.map((pos: any, i: number) => (
                      <tr key={i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                        <td style={{ fontFamily: "monospace" }}>{pos.symbol}</td>
                        <td style={{ color: pos.side === "buy" ? "#0a7" : "#c22" }}>{pos.side.toUpperCase()}</td>
                        <td>{pos.entry_price?.toFixed(2)}</td>
                        <td>{pos.current_price?.toFixed(2)}</td>
                        <td>{pos.stop?.toFixed(2) ?? "—"}</td>
                        <td>{pos.tp?.toFixed(2) ?? "—"}</td>
                        <td style={{ color: pos.unrealized_pnl_pct >= 0 ? "#0a7" : "#c22", fontWeight: 600 }}>
                          {pos.unrealized_pnl_pct >= 0 ? "+" : ""}{pos.unrealized_pnl_pct?.toFixed(2)}% (${pos.unrealized_pnl_quote?.toFixed(2)})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Closed trades */}
            {paperTrades?.trades?.length > 0 && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <h3 style={{ margin: 0 }}>📈 Paper Trade History</h3>
                  {paperTrades.summary && (
                    <div style={{ fontSize: 13 }}>
                      <span style={{ marginRight: 12 }}>
                        W/L: <strong>{paperTrades.summary.wins}/{paperTrades.summary.losses}</strong> ({paperTrades.summary.win_rate?.toFixed(0)}%)
                      </span>
                      <span style={{ color: paperTrades.summary.total_pnl >= 0 ? "#0a7" : "#c22", fontWeight: 600 }}>
                        Total: ${paperTrades.summary.total_pnl?.toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
                <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Entry</th>
                      <th>Exit</th>
                      <th>Reason</th>
                      <th>P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paperTrades.trades.slice().reverse().map((t: any, i: number) => (
                      <tr key={i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                        <td style={{ fontFamily: "monospace" }}>{t.symbol}</td>
                        <td style={{ color: t.side === "buy" ? "#0a7" : "#c22" }}>{t.side.toUpperCase()}</td>
                        <td>{t.entry_price?.toFixed(2)}</td>
                        <td>{t.exit_price?.toFixed(2)}</td>
                        <td>{t.exit_reason === "tp" ? "🎯 TP" : "🛑 Stop"}</td>
                        <td style={{ color: t.pnl_pct >= 0 ? "#0a7" : "#c22", fontWeight: 600 }}>
                          {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct?.toFixed(2)}% (${t.pnl_quote?.toFixed(2)})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {openPositions.length === 0 && (!paperTrades?.trades || paperTrades.trades.length === 0) && (
              <p style={{ color: "#666" }}>No paper trades yet. Waiting for signals...</p>
            )}
          </div>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <h2>Latest candle ({baseInterval})</h2>
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
