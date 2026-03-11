import httpx
from typing import List, Dict, Any

BINANCE_BASE = "https://api.binance.com"

async def fetch_klines(symbol: str, interval: str = "3m", startTime: int | None = None, endTime: int | None = None, limit: int = 1000) -> List[List[Any]]:
    params: Dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
    if startTime is not None:
        params["startTime"] = startTime
    if endTime is not None:
        params["endTime"] = endTime

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{BINANCE_BASE}/api/v3/klines", params=params)
        r.raise_for_status()
        return r.json()
