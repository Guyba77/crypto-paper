from __future__ import annotations

import asyncio
import json
from typing import Dict, Any, List

import websockets


def _streams(symbols: List[str]) -> str:
    # Binance expects lowercase symbols
    parts = []
    for s in symbols:
        sym = s.lower()
        parts.append(f"{sym}@kline_3m")
        parts.append(f"{sym}@kline_15m")
    return "/".join(parts)


async def binance_kline_stream(symbols: List[str]):
    url = f"wss://stream.binance.com:9443/stream?streams={_streams(symbols)}"
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        async for msg in ws:
            data = json.loads(msg)
            payload: Dict[str, Any] = data.get("data", {})
            if payload.get("e") != "kline":
                continue
            k = payload.get("k", {})
            yield {
                "symbol": payload.get("s"),
                "interval": k.get("i"),
                "closed": bool(k.get("x")),
                "t": int(k.get("t")),
                "o": float(k.get("o")),
                "h": float(k.get("h")),
                "l": float(k.get("l")),
                "c": float(k.get("c")),
                "v": float(k.get("v")),
            }


async def reconnecting_stream(symbols: List[str], backoff_s: float = 1.0, max_backoff_s: float = 30.0):
    delay = backoff_s
    while True:
        try:
            async for ev in binance_kline_stream(symbols):
                delay = backoff_s
                yield ev
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # backoff and retry
            await asyncio.sleep(delay)
            delay = min(max_backoff_s, delay * 1.7)
