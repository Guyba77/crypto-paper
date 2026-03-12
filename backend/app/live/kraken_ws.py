from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import websockets

from ..services.kraken_ohlc import interval_to_minutes


def _itv_str(interval: str) -> str:
    # normalize to '5m'/'15m'/'1h' strings
    s = interval.strip().lower()
    if s.endswith("m") or s.endswith("h") or s.endswith("d"):
        return s
    # raw minutes
    m = int(s)
    return f"{m}m"


async def kraken_ohlc_stream(pairs: List[str], intervals: List[str]):
    """Subscribe to Kraken WS OHLC feed for given pairs/intervals.

    Yields events in a unified format:
      { symbol: <pair>, interval: '5m', closed: bool, t: ms, o,h,l,c,v }

    Kraken OHLC messages look like:
      [channelID, [time, etime, open, high, low, close, vwap, volume, count, closed], "ohlc-5", "XBT/USD"]
    where closed is "0" or "1".
    """

    url = "wss://ws.kraken.com/"

    # Kraken subscribe message supports one interval per subscription.
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        for itv in intervals:
            minutes = interval_to_minutes(itv)
            sub = {
                "event": "subscribe",
                "pair": pairs,
                "subscription": {"name": "ohlc", "interval": minutes},
            }
            await ws.send(json.dumps(sub))

        async for msg in ws:
            data = json.loads(msg)
            if isinstance(data, dict):
                # systemStatus/subscriptionStatus/heartbeat
                continue
            if not isinstance(data, list) or len(data) < 4:
                continue

            # data: [chanId, ohlcArr, chanName, pair]
            _, ohlc, chan_name, pair = data[0], data[1], data[2], data[3]
            if not isinstance(ohlc, list) or len(ohlc) < 9:
                continue

            # channel name looks like 'ohlc-5'
            itv_minutes: Optional[int] = None
            try:
                if isinstance(chan_name, str) and chan_name.startswith("ohlc-"):
                    itv_minutes = int(chan_name.split("-")[1])
            except Exception:
                itv_minutes = None

            # closed flag is last element
            closed_flag = str(ohlc[-1])
            closed = closed_flag == "1"

            # time is seconds
            t_s = int(float(ohlc[0]))
            ev = {
                "symbol": str(pair),
                "interval": f"{itv_minutes}m" if itv_minutes else _itv_str("5m"),
                "closed": closed,
                "t": t_s * 1000,
                "o": float(ohlc[2]),
                "h": float(ohlc[3]),
                "l": float(ohlc[4]),
                "c": float(ohlc[5]),
                "v": float(ohlc[7]),
            }
            yield ev


async def reconnecting_stream(pairs: List[str], intervals: List[str], backoff_s: float = 1.0, max_backoff_s: float = 30.0):
    delay = backoff_s
    while True:
        try:
            async for ev in kraken_ohlc_stream(pairs, intervals):
                delay = backoff_s
                yield ev
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(delay)
            delay = min(max_backoff_s, delay * 1.7)
