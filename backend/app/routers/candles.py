from fastapi import APIRouter, Query
from datetime import datetime, timezone

from ..services.binance import fetch_klines_paged

router = APIRouter()

@router.get("/candles")
async def get_candles(
    symbol: str,
    interval: str = Query(default="3m"),
    limit: int = Query(default=500, ge=1, le=5000),
):
    # Proxy to Binance with paging support.
    raw = await fetch_klines_paged(symbol=symbol, interval=interval, max_candles=limit)

    candles = []
    for k in raw:
        open_time = int(k[0])
        candles.append({
            "t": open_time,
            "time": datetime.fromtimestamp(open_time/1000, tz=timezone.utc).isoformat(),
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
        })

    return {"symbol": symbol, "interval": interval, "candles": candles}
