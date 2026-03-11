import httpx
from typing import List, Dict, Any, Optional

BINANCE_BASE = "https://api.binance.com"


async def fetch_klines(
    symbol: str,
    interval: str = "3m",
    startTime: int | None = None,
    endTime: int | None = None,
    limit: int = 1000,
) -> List[List[Any]]:
    params: Dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
    if startTime is not None:
        params["startTime"] = startTime
    if endTime is not None:
        params["endTime"] = endTime

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{BINANCE_BASE}/api/v3/klines", params=params)
        r.raise_for_status()
        return r.json()


async def fetch_klines_paged(
    *,
    symbol: str,
    interval: str,
    startTime: Optional[int] = None,
    endTime: Optional[int] = None,
    max_candles: int = 5000,
) -> List[List[Any]]:
    """Fetch more than 1000 candles by paging Binance requests.

    Notes:
    - Binance caps each call at 1000 candles.
    - We page forward using startTime = last_open_time + 1ms.
    """
    out: List[List[Any]] = []
    cursor = startTime

    while True:
        remaining = max_candles - len(out)
        if remaining <= 0:
            break
        limit = min(1000, remaining)

        batch = await fetch_klines(symbol=symbol, interval=interval, startTime=cursor, endTime=endTime, limit=limit)
        if not batch:
            break

        out.extend(batch)
        last_open = int(batch[-1][0])

        # stop if we didn't fill a full page (no more data)
        if len(batch) < limit:
            break

        # advance cursor (avoid repeating the last candle)
        cursor = last_open + 1

        # safety: if endTime is set and we've reached/passed it, stop
        if endTime is not None and last_open >= endTime:
            break

    # Trim any candles beyond endTime (Binance can return the candle starting before endTime)
    if endTime is not None:
        out = [k for k in out if int(k[0]) <= endTime]

    return out
