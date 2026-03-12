from fastapi import APIRouter
from pydantic import BaseModel, Field
import numpy as np

from ..services.kraken_ohlc import fetch_ohlc_paged, interval_to_minutes
from ..backtest.engine import backtest_ema_cross, backtest_rsi_mean_reversion

router = APIRouter()

class BacktestRequest(BaseModel):
    symbol: str
    interval: str = "5m"

    # Backtest window controls:
    # - days: fetch N days back from now (approx, based on candle count)
    # - start_time/end_time: ms since epoch (Binance startTime/endTime)
    days: int | None = Field(default=7, ge=1, le=365)
    start_time: int | None = None
    end_time: int | None = None

    # safety cap
    max_candles: int = Field(default=20000, ge=50, le=200000)

    strategy: str  # 'ema_cross' | 'rsi_mean_reversion'
    params: dict = {}

    initial_cash: float = 1000.0
    fee_bps: float = 10.0
    slippage_bps: float = 2.0


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    # Determine window
    end_time = req.end_time
    start_time = req.start_time

    if start_time is None and end_time is None and req.days is not None:
        # approximate candles needed based on interval
        def _interval_minutes(itv: str) -> int | None:
            try:
                if itv.endswith("m"):
                    return int(itv[:-1])
                if itv.endswith("h"):
                    return int(itv[:-1]) * 60
                if itv.endswith("d"):
                    return int(itv[:-1]) * 60 * 24
            except Exception:
                return None
            return None

        mins = _interval_minutes(req.interval)
        if mins and mins > 0:
            per_day = max(1, int(1440 / mins))
            approx = int(req.days * per_day)
        else:
            approx = int(req.days * 1000)

        max_candles = min(req.max_candles, max(approx, 500))
    else:
        max_candles = req.max_candles

    # Kraken OHLC uses 'since' (seconds). We'll approximate "days" by candle count; for now ignore end_time.
    raw = fetch_ohlc_paged(
        pair=req.symbol,
        interval=req.interval,
        max_candles=max_candles,
        since_ms=start_time,
    )

    # k: [time_s, open, high, low, close, vwap, volume, count]
    t = np.array([int(k[0]) * 1000 for k in raw], dtype=np.int64)
    o = np.array([float(k[1]) for k in raw], dtype=float)
    h = np.array([float(k[2]) for k in raw], dtype=float)
    l = np.array([float(k[3]) for k in raw], dtype=float)
    c = np.array([float(k[4]) for k in raw], dtype=float)

    # risk model: swing stop (lookback lows/highs) + fixed R:R take-profit
    risk = {
        "stop_lookback": int(req.params.get("stop_lookback", 11)),
        "rr": float(req.params.get("rr", 3.0)),
        # if both stop and TP are touched in same candle, assume stop first (conservative)
        "same_bar_priority": str(req.params.get("same_bar_priority", "stop")),
        # MA type for EMA/SMA cross strategy
        "ma_type": str(req.params.get("ma_type", "ema")),
        # direction filter
        "direction": str(req.params.get("direction", "both")),
    }

    # trend filter (higher timeframe MA)
    trend = {
        "enabled": bool(req.params.get("trend_enabled", True)),
        "interval": str(req.params.get("trend_interval", "15m")),
        "ma_type": str(req.params.get("trend_ma_type", "ema")),
        "period": int(req.params.get("trend_period", 200)),
    }

    # compute trend MA series on higher timeframe and align to base candles
    trend_ma = None
    if trend["enabled"]:
        raw_trend = fetch_ohlc_paged(pair=req.symbol, interval=trend["interval"], max_candles=1000)
        t2 = np.array([int(k[0]) * 1000 for k in raw_trend], dtype=np.int64)
        c2 = np.array([float(k[4]) for k in raw_trend], dtype=float)
        from ..backtest.indicators import ema as ema_fn, sma as sma_fn
        ma2 = (ema_fn if trend["ma_type"] == "ema" else sma_fn)(c2, trend["period"])
        # align: for each base candle time, use last MA where t2 <= t
        idx = np.searchsorted(t2, t, side="right") - 1
        trend_ma = np.where(idx >= 0, ma2[np.clip(idx, 0, len(ma2)-1)], np.nan)

    if req.strategy == "ema_cross":
        fast = int(req.params.get("fast", 20))
        slow = int(req.params.get("slow", 50))
        result = backtest_ema_cross(t, o, h, l, c, fast, slow, req.initial_cash, req.fee_bps, req.slippage_bps, risk, trend_ma)
    elif req.strategy == "rsi_mean_reversion":
        period = int(req.params.get("period", 14))
        buy_below = float(req.params.get("buy_below", 30))
        sell_above = float(req.params.get("sell_above", 70))
        result = backtest_rsi_mean_reversion(t, o, h, l, c, period, buy_below, sell_above, req.initial_cash, req.fee_bps, req.slippage_bps, risk, trend_ma)
    else:
        return {"error": f"unknown strategy: {req.strategy}"}

    # quick stats
    equity = result["equity"]
    if equity:
        start = equity[0]["equity"]
        end = equity[-1]["equity"]
        result["stats"] = {
            "start_equity": start,
            "end_equity": end,
            "return_pct": (end - start) / start * 100.0 if start else None,
            "trades": len(result["trades"]),
        }

    return {
        "symbol": req.symbol,
        "interval": req.interval,
        "strategy": req.strategy,
        "params": req.params,
        **result,
    }
