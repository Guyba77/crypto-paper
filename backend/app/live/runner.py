from __future__ import annotations

import asyncio
from typing import Dict, Any, List, Optional
import numpy as np

from .state import STATE, RunnerConfig, MarketState, now_ms
from .binance_ws import reconnecting_stream
from ..backtest.indicators import ema, sma
from ..backtest.engine import backtest_ema_cross, backtest_rsi_mean_reversion
from ..services.binance import fetch_klines_paged


def _ma_fn(ma_type: str):
    return ema if ma_type == "ema" else sma


class CandleBuffer:
    def __init__(self, maxlen: int = 5000):
        self.maxlen = maxlen
        self.t: List[int] = []
        self.o: List[float] = []
        self.h: List[float] = []
        self.l: List[float] = []
        self.c: List[float] = []
        self.v: List[float] = []

    def append(self, ev: Dict[str, Any]):
        self.t.append(int(ev["t"]))
        self.o.append(float(ev["o"]))
        self.h.append(float(ev["h"]))
        self.l.append(float(ev["l"]))
        self.c.append(float(ev["c"]))
        self.v.append(float(ev["v"]))
        if len(self.t) > self.maxlen:
            for arr in (self.t, self.o, self.h, self.l, self.c, self.v):
                del arr[: len(arr) - self.maxlen]

    def np(self):
        return (
            np.array(self.t, dtype=np.int64),
            np.array(self.o, dtype=float),
            np.array(self.h, dtype=float),
            np.array(self.l, dtype=float),
            np.array(self.c, dtype=float),
        )


class LiveRunner:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._buffers_base: Dict[str, CandleBuffer] = {}
        self._buffers_trend: Dict[str, CandleBuffer] = {}

    async def start(self, cfg: RunnerConfig):
        if STATE.running:
            return
        STATE.running = True
        STATE.started_at = asyncio.get_event_loop().time()
        STATE.last_error = None
        STATE.config = cfg
        STATE.markets = {s: MarketState(symbol=s) for s in cfg.symbols}

        # seed candle buffers with some history so signals work immediately
        await self._seed(cfg)

        self._task = asyncio.create_task(self._run(cfg))

    async def stop(self):
        STATE.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        self._task = None

    async def _seed(self, cfg: RunnerConfig):
        # seed with ~days_seed worth of data for both 3m and 15m
        for sym in cfg.symbols:
            b_base = CandleBuffer(maxlen=20000)
            b_trend = CandleBuffer(maxlen=5000)
            self._buffers_base[sym] = b_base
            self._buffers_trend[sym] = b_trend

            # Rough candles/day: 1440 / minutes. Default to 480/day (3m) if unparseable.
            minutes = 3
            try:
                if cfg.base_interval.endswith("m"):
                    minutes = int(cfg.base_interval[:-1])
                elif cfg.base_interval.endswith("h"):
                    minutes = int(cfg.base_interval[:-1]) * 60
            except Exception:
                minutes = 3
            per_day = max(1, int(1440 / minutes))

            max_base = min(20000, max(1000, cfg.days_seed * per_day))
            raw_base = await fetch_klines_paged(symbol=sym, interval=cfg.base_interval, max_candles=max_base)
            for k in raw_base:
                b_base.append({"t": int(k[0]), "o": k[1], "h": k[2], "l": k[3], "c": k[4], "v": k[5]})

            raw_trend = await fetch_klines_paged(symbol=sym, interval=cfg.trend_interval, max_candles=1000)
            for k in raw_trend:
                b_trend.append({"t": int(k[0]), "o": k[1], "h": k[2], "l": k[3], "c": k[4], "v": k[5]})

    async def _run(self, cfg: RunnerConfig):
        try:
            async for ev in reconnecting_stream(cfg.symbols, [cfg.base_interval, cfg.trend_interval]):
                if not STATE.running:
                    break
                sym = ev["symbol"]
                interval = ev["interval"]
                if not ev["closed"]:
                    continue

                if interval == cfg.base_interval:
                    self._buffers_base[sym].append(ev)
                    await self._on_base_close(sym, cfg)
                elif interval == cfg.trend_interval:
                    self._buffers_trend[sym].append(ev)
                    self._update_trend(sym, cfg)
        except asyncio.CancelledError:
            return
        except Exception as e:
            STATE.last_error = repr(e)
            STATE.running = False

    def _update_trend(self, sym: str, cfg: RunnerConfig):
        b15 = self._buffers_trend.get(sym)
        if not b15:
            return
        t, o, h, l, c = b15.np()
        ma_type = str(cfg.params.get("trend_ma_type", "ema"))
        period = int(cfg.params.get("trend_period", 200))
        ma = _ma_fn(ma_type)(c, period)
        last = float(ma[-1]) if len(ma) else None
        STATE.markets[sym].trend_ma = last

    async def _on_base_close(self, sym: str, cfg: RunnerConfig):
        m = STATE.markets[sym]
        b = self._buffers_base[sym]
        t, o, h, l, c = b.np()
        m.last_update_ms = int(t[-1]) if len(t) else None
        m.last_price = float(c[-1]) if len(c) else None
        self._update_trend(sym, cfg)

        # Build aligned trend series (constant last trend for now; good enough for screener)
        trend_val = m.trend_ma
        trend_series = None
        if trend_val is not None:
            trend_series = np.full_like(c, trend_val, dtype=float)

        # Use existing backtest engines to decide the *next* entry signal by looking at last bar
        # We run a tiny backtest on the buffered candles and inspect last trade for entry.
        risk = {
            "stop_lookback": int(cfg.params.get("stop_lookback", 11)),
            "rr": float(cfg.params.get("rr", 3.0)),
            "same_bar_priority": "stop",
            "ma_type": str(cfg.params.get("ma_type", "ema")),
            "direction": str(cfg.params.get("direction", "both")),
        }

        # For screener, we only want to know whether an entry would trigger on this close.
        # We'll emulate that by running the strategy and checking the last trade meta.
        if cfg.strategy == "ema_cross":
            fast = int(cfg.params.get("fast", 7))
            slow = int(cfg.params.get("slow", 18))
            result = backtest_ema_cross(t, o, h, l, c, fast, slow, 1000.0, 0.0, 0.0, risk, trend_series)
        else:
            period = int(cfg.params.get("period", 14))
            buy_below = float(cfg.params.get("buy_below", 30))
            sell_above = float(cfg.params.get("sell_above", 70))
            result = backtest_rsi_mean_reversion(t, o, h, l, c, period, buy_below, sell_above, 1000.0, 0.0, 0.0, risk, trend_series)

        sig = None
        meta: Dict[str, Any] = {}
        trades = result.get("trades", [])
        if trades:
            last = trades[-1]
            if last.get("meta", {}).get("reason") == "entry" and last.get("t") == int(t[-1]):
                dir_ = last.get("meta", {}).get("dir")
                sig = "enter_long" if dir_ == "long" else "enter_short"
                meta = last.get("meta", {})

        m.signal = sig
        m.signal_meta = meta


RUNNER = LiveRunner()
