from fastapi import APIRouter
from pydantic import BaseModel, Field
import numpy as np

from ..services.binance import fetch_klines
from ..backtest.engine import backtest_ema_cross, backtest_rsi_mean_reversion

router = APIRouter()

class BacktestRequest(BaseModel):
    symbol: str
    interval: str = "3m"
    limit: int = Field(default=1000, ge=50, le=1000)

    strategy: str  # 'ema_cross' | 'rsi_mean_reversion'
    params: dict = {}

    initial_cash: float = 1000.0
    fee_bps: float = 10.0
    slippage_bps: float = 2.0


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    raw = await fetch_klines(symbol=req.symbol, interval=req.interval, limit=req.limit)
    t = np.array([int(k[0]) for k in raw], dtype=np.int64)
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
    }

    if req.strategy == "ema_cross":
        fast = int(req.params.get("fast", 20))
        slow = int(req.params.get("slow", 50))
        result = backtest_ema_cross(t, o, h, l, c, fast, slow, req.initial_cash, req.fee_bps, req.slippage_bps, risk)
    elif req.strategy == "rsi_mean_reversion":
        period = int(req.params.get("period", 14))
        buy_below = float(req.params.get("buy_below", 30))
        sell_above = float(req.params.get("sell_above", 70))
        result = backtest_rsi_mean_reversion(t, o, h, l, c, period, buy_below, sell_above, req.initial_cash, req.fee_bps, req.slippage_bps, risk)
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
