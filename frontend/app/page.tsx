"use client";

import { useEffect, useMemo, useState } from "react";

type Candle = { t: number; o: number; h: number; l: number; c: number; v: number };

const API = "http://localhost:8000";

export default function HomePage() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbol, setSymbol] = useState<string>("BTCUSDT");
  const [candles, setCandles] = useState<Candle[]>([]);

  const [strategy, setStrategy] = useState<string>("ema_cross");
  const [params, setParams] = useState<Record<string, string>>({ fast: "20", slow: "50", stop_lookback: "11", rr: "3", ma_type: "ema", trend_enabled: "1", trend_interval: "15m", trend_ma_type: "ema", trend_period: "200" });
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    fetch(`${API}/api/symbols`).then(r => r.json()).then(d => setSymbols(d.symbols));
  }, []);

  useEffect(() => {
    fetch(`${API}/api/candles?symbol=${encodeURIComponent(symbol)}&interval=3m&limit=300`)
      .then(r => r.json())
      .then(d => setCandles(d.candles));
  }, [symbol]);

  const last = useMemo(() => candles[candles.length - 1], [candles]);

  async function runBacktest() {
    const payload = {
      symbol,
      interval: "3m",
      limit: 1000,
      strategy,
      params: Object.fromEntries(
        Object.entries(params).map(([k, v]) => {
          if (k === "trend_interval") return [k, v];
          if (k === "ma_type") return [k, v];
          if (k === "trend_ma_type") return [k, v];
          if (k === "trend_enabled") return [k, v === "1" || v.toLowerCase() === "true"];
          return [k, Number(v)];
        })
      ),
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
          Strategy:{" "}
          <select
            value={strategy}
            onChange={(e) => {
              const v = e.target.value;
              setStrategy(v);
              setParams(
                v === "ema_cross"
                  ? { fast: "20", slow: "50", stop_lookback: "11", rr: "3", ma_type: "ema", trend_enabled: "1", trend_interval: "15m", trend_ma_type: "ema", trend_period: "200" }
                  : { period: "14", buy_below: "30", sell_above: "70", stop_lookback: "11", rr: "3", trend_enabled: "1", trend_interval: "15m", trend_ma_type: "ema", trend_period: "200" }
              );
            }}
          >
            <option value="ema_cross">EMA cross</option>
            <option value="rsi_mean_reversion">RSI mean reversion</option>
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

      <footer style={{ marginTop: 24, color: "#666" }}>
        <small>Not financial advice. Paper/backtest only.</small>
      </footer>
    </main>
  );
}
