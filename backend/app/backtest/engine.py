from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any, List
import numpy as np

from .indicators import ema, rsi

Side = Literal["buy", "sell"]

@dataclass
class Trade:
    t: int
    side: Side
    price: float
    qty: float
    fee: float


def backtest_ema_cross(
    t: np.ndarray,
    close: np.ndarray,
    fast: int,
    slow: int,
    initial_cash: float,
    fee_bps: float,
    slippage_bps: float,
) -> Dict[str, Any]:
    ef = ema(close, fast)
    es = ema(close, slow)

    cash = initial_cash
    pos = 0.0
    trades: List[Trade] = []
    equity = []

    def exec_fill(side: Side, price: float, qty: float, ts: int):
        nonlocal cash, pos
        slip = price * (slippage_bps / 10000.0)
        fill_price = price + slip if side == "buy" else price - slip
        notional = fill_price * qty
        fee = notional * (fee_bps / 10000.0)
        if side == "buy":
            cash -= notional + fee
            pos += qty
        else:
            cash += notional - fee
            pos -= qty
        trades.append(Trade(t=ts, side=side, price=fill_price, qty=qty, fee=fee))

    for i in range(1, len(close)):
        # mark-to-market equity
        equity.append({"t": int(t[i]), "equity": float(cash + pos * close[i])})

        # signal on cross
        prev = ef[i-1] - es[i-1]
        curr = ef[i] - es[i]
        if prev <= 0 and curr > 0:
            # go long with all cash
            if pos == 0 and cash > 0:
                qty = cash / close[i]
                exec_fill("buy", close[i], qty, int(t[i]))
        elif prev >= 0 and curr < 0:
            # exit
            if pos > 0:
                exec_fill("sell", close[i], pos, int(t[i]))

    # final equity point
    if len(close) > 0:
        equity.append({"t": int(t[-1]), "equity": float(cash + pos * close[-1])})

    return {
        "trades": [trade.__dict__ for trade in trades],
        "equity": equity,
    }


def backtest_rsi_mean_reversion(
    t: np.ndarray,
    close: np.ndarray,
    period: int,
    buy_below: float,
    sell_above: float,
    initial_cash: float,
    fee_bps: float,
    slippage_bps: float,
) -> Dict[str, Any]:
    r = rsi(close, period)

    cash = initial_cash
    pos = 0.0
    trades: List[Trade] = []
    equity = []

    def exec_fill(side: Side, price: float, qty: float, ts: int):
        nonlocal cash, pos
        slip = price * (slippage_bps / 10000.0)
        fill_price = price + slip if side == "buy" else price - slip
        notional = fill_price * qty
        fee = notional * (fee_bps / 10000.0)
        if side == "buy":
            cash -= notional + fee
            pos += qty
        else:
            cash += notional - fee
            pos -= qty
        trades.append(Trade(t=ts, side=side, price=fill_price, qty=qty, fee=fee))

    for i in range(1, len(close)):
        equity.append({"t": int(t[i]), "equity": float(cash + pos * close[i])})

        if pos == 0 and r[i] <= buy_below and cash > 0:
            qty = cash / close[i]
            exec_fill("buy", close[i], qty, int(t[i]))
        elif pos > 0 and r[i] >= sell_above:
            exec_fill("sell", close[i], pos, int(t[i]))

    if len(close) > 0:
        equity.append({"t": int(t[-1]), "equity": float(cash + pos * close[-1])})

    return {
        "trades": [trade.__dict__ for trade in trades],
        "equity": equity,
    }
