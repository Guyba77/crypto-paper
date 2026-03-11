from __future__ import annotations

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any, List, Optional
import numpy as np

from .indicators import ema, sma, rsi

Side = Literal["buy", "sell"]

@dataclass
class Trade:
    t: int
    side: Side
    price: float
    qty: float
    fee: float
    meta: Dict[str, Any]


def _exec_fill(
    *,
    side: Side,
    price: float,
    qty: float,
    ts: int,
    cash: float,
    pos: float,
    fee_bps: float,
    slippage_bps: float,
    meta: Optional[Dict[str, Any]] = None,
) -> tuple[float, float, Trade]:
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
    return cash, pos, Trade(t=ts, side=side, price=float(fill_price), qty=float(qty), fee=float(fee), meta=meta or {})


def _swing_stop(
    *,
    side: Literal["long", "short"],
    highs: np.ndarray,
    lows: np.ndarray,
    i: int,
    lookback: int,
) -> float | None:
    # Uses the prior `lookback` fully-formed candles, excluding the entry candle at index i.
    start = i - lookback
    end = i
    if start < 0:
        return None
    if side == "long":
        return float(np.min(lows[start:end]))
    else:
        return float(np.max(highs[start:end]))


def _check_exits_same_bar_conservative(
    *,
    side: Literal["long", "short"],
    hi: float,
    lo: float,
    stop: float,
    tp: float,
    priority: str,
) -> str | None:
    # Returns 'stop' | 'tp' | None
    stop_hit = lo <= stop if side == "long" else hi >= stop
    tp_hit = hi >= tp if side == "long" else lo <= tp

    if not stop_hit and not tp_hit:
        return None
    if stop_hit and tp_hit:
        return "stop" if priority == "stop" else "tp"
    return "stop" if stop_hit else "tp"


def backtest_ema_cross(
    t: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    fast: int,
    slow: int,
    initial_cash: float,
    fee_bps: float,
    slippage_bps: float,
    risk: Dict[str, Any],
    trend_ma: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    # MA type for entry signal: 'ema' | 'sma'
    ma_type = str(risk.get("ma_type", "ema"))
    ma_fn = ema if ma_type == "ema" else sma
    ef = ma_fn(c, fast)
    es = ma_fn(c, slow)

    cash = float(initial_cash)
    pos = 0.0  # positive=long qty, negative=short qty
    entry_price: float | None = None
    stop_price: float | None = None
    tp_price: float | None = None

    trades: List[Trade] = []
    equity = []

    lookback = int(risk.get("stop_lookback", 11))
    rr = float(risk.get("rr", 3.0))
    priority = str(risk.get("same_bar_priority", "stop"))
    direction = str(risk.get("direction", "both"))  # 'long'|'short'|'both'

    for i in range(1, len(c)):
        equity.append({"t": int(t[i]), "equity": float(cash + pos * c[i])})

        # Manage open position exits (stop/tp)
        if pos != 0 and stop_price is not None and tp_price is not None:
            side = "long" if pos > 0 else "short"
            hit = _check_exits_same_bar_conservative(side=side, hi=float(h[i]), lo=float(l[i]), stop=stop_price, tp=tp_price, priority=priority)
            if hit == "stop":
                exit_px = stop_price
                exit_side: Side = "sell" if pos > 0 else "buy"
                cash, pos, tr = _exec_fill(side=exit_side, price=exit_px, qty=abs(pos), ts=int(t[i]), cash=cash, pos=pos, fee_bps=fee_bps, slippage_bps=slippage_bps, meta={"reason": "stop"})
                trades.append(tr)
                entry_price = stop_price = tp_price = None
            elif hit == "tp":
                exit_px = tp_price
                exit_side = "sell" if pos > 0 else "buy"
                cash, pos, tr = _exec_fill(side=exit_side, price=exit_px, qty=abs(pos), ts=int(t[i]), cash=cash, pos=pos, fee_bps=fee_bps, slippage_bps=slippage_bps, meta={"reason": "tp"})
                trades.append(tr)
                entry_price = stop_price = tp_price = None

        # Signal logic (EMA cross) only enters if flat
        prev = ef[i - 1] - es[i - 1]
        curr = ef[i] - es[i]

        if pos == 0:
            if direction in ("both", "long") and prev <= 0 and curr > 0:
                # enter long (trend filter: price above HTF MA)
                if trend_ma is None or (not np.isnan(trend_ma[i]) and c[i] > trend_ma[i]):
                    stop = _swing_stop(side="long", highs=h, lows=l, i=i, lookback=lookback)
                    if stop is not None:
                        entry = float(c[i])
                        dist = entry - stop
                        if dist > 0:
                            tp = entry + rr * dist
                            qty = cash / entry
                            cash, pos, tr = _exec_fill(
                                side="buy",
                                price=entry,
                                qty=qty,
                                ts=int(t[i]),
                                cash=cash,
                                pos=pos,
                                fee_bps=fee_bps,
                                slippage_bps=slippage_bps,
                                meta={"reason": "entry", "dir": "long", "stop": stop, "tp": tp, "trend_ma": None if trend_ma is None else float(trend_ma[i])},
                            )
                            trades.append(tr)
                            entry_price, stop_price, tp_price = entry, stop, tp

            elif direction in ("both", "short") and prev >= 0 and curr < 0:
                # enter short (trend filter: price below HTF MA)
                if trend_ma is None or (not np.isnan(trend_ma[i]) and c[i] < trend_ma[i]):
                    stop = _swing_stop(side="short", highs=h, lows=l, i=i, lookback=lookback)
                    if stop is not None:
                        entry = float(c[i])
                        dist = stop - entry
                        if dist > 0:
                            tp = entry - rr * dist
                            qty = cash / entry
                            cash, pos, tr = _exec_fill(
                                side="sell",
                                price=entry,
                                qty=qty,
                                ts=int(t[i]),
                                cash=cash,
                                pos=pos,
                                fee_bps=fee_bps,
                                slippage_bps=slippage_bps,
                                meta={"reason": "entry", "dir": "short", "stop": stop, "tp": tp, "trend_ma": None if trend_ma is None else float(trend_ma[i])},
                            )
                            trades.append(tr)
                            entry_price, stop_price, tp_price = entry, stop, tp

    if len(c) > 0:
        equity.append({"t": int(t[-1]), "equity": float(cash + pos * c[-1])})

    return {"trades": [trade.__dict__ for trade in trades], "equity": equity}


def backtest_rsi_mean_reversion(
    t: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    period: int,
    buy_below: float,
    sell_above: float,
    initial_cash: float,
    fee_bps: float,
    slippage_bps: float,
    risk: Dict[str, Any],
    trend_ma: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    r = rsi(c, period)

    cash = float(initial_cash)
    pos = 0.0
    stop_price: float | None = None
    tp_price: float | None = None

    trades: List[Trade] = []
    equity = []

    lookback = int(risk.get("stop_lookback", 11))
    rr = float(risk.get("rr", 3.0))
    priority = str(risk.get("same_bar_priority", "stop"))
    direction = str(risk.get("direction", "both"))  # 'long'|'short'|'both'

    for i in range(1, len(c)):
        equity.append({"t": int(t[i]), "equity": float(cash + pos * c[i])})

        # exits
        if pos != 0 and stop_price is not None and tp_price is not None:
            side = "long" if pos > 0 else "short"
            hit = _check_exits_same_bar_conservative(side=side, hi=float(h[i]), lo=float(l[i]), stop=stop_price, tp=tp_price, priority=priority)
            if hit == "stop":
                exit_side: Side = "sell" if pos > 0 else "buy"
                cash, pos, tr = _exec_fill(side=exit_side, price=stop_price, qty=abs(pos), ts=int(t[i]), cash=cash, pos=pos, fee_bps=fee_bps, slippage_bps=slippage_bps, meta={"reason": "stop"})
                trades.append(tr)
                stop_price = tp_price = None
            elif hit == "tp":
                exit_side = "sell" if pos > 0 else "buy"
                cash, pos, tr = _exec_fill(side=exit_side, price=tp_price, qty=abs(pos), ts=int(t[i]), cash=cash, pos=pos, fee_bps=fee_bps, slippage_bps=slippage_bps, meta={"reason": "tp"})
                trades.append(tr)
                stop_price = tp_price = None

        # entries
        if pos == 0:
            if direction in ("both", "long") and r[i] <= buy_below:
                # enter long only if above HTF MA
                if trend_ma is None or (not np.isnan(trend_ma[i]) and c[i] > trend_ma[i]):
                    stop = _swing_stop(side="long", highs=h, lows=l, i=i, lookback=lookback)
                    if stop is not None:
                        entry = float(c[i])
                        dist = entry - stop
                        if dist > 0:
                            tp = entry + rr * dist
                            qty = cash / entry
                            cash, pos, tr = _exec_fill(
                                side="buy",
                                price=entry,
                                qty=qty,
                                ts=int(t[i]),
                                cash=cash,
                                pos=pos,
                                fee_bps=fee_bps,
                                slippage_bps=slippage_bps,
                                meta={"reason": "entry", "dir": "long", "stop": stop, "tp": tp, "trend_ma": None if trend_ma is None else float(trend_ma[i])},
                            )
                            trades.append(tr)
                            stop_price, tp_price = stop, tp

            elif direction in ("both", "short") and r[i] >= sell_above:
                # enter short only if below HTF MA
                if trend_ma is None or (not np.isnan(trend_ma[i]) and c[i] < trend_ma[i]):
                    stop = _swing_stop(side="short", highs=h, lows=l, i=i, lookback=lookback)
                    if stop is not None:
                        entry = float(c[i])
                        dist = stop - entry
                        if dist > 0:
                            tp = entry - rr * dist
                            qty = cash / entry
                            cash, pos, tr = _exec_fill(
                                side="sell",
                                price=entry,
                                qty=qty,
                                ts=int(t[i]),
                                cash=cash,
                                pos=pos,
                                fee_bps=fee_bps,
                                slippage_bps=slippage_bps,
                                meta={"reason": "entry", "dir": "short", "stop": stop, "tp": tp, "trend_ma": None if trend_ma is None else float(trend_ma[i])},
                            )
                            trades.append(tr)
                            stop_price, tp_price = stop, tp

    if len(c) > 0:
        equity.append({"t": int(t[-1]), "equity": float(cash + pos * c[-1])})

    return {"trades": [trade.__dict__ for trade in trades], "equity": equity}
