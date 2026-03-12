from fastapi import APIRouter, Query
from datetime import datetime, timezone

from ..services.kraken_ohlc import fetch_ohlc_paged

router = APIRouter()

@router.get("/candles")
async def get_candles(
    symbol: str,
    interval: str = Query(default="5m"),
    limit: int = Query(default=500, ge=1, le=5000),
):
    # Proxy to Kraken OHLC with paging support.
    raw = fetch_ohlc_paged(pair=symbol, interval=interval, max_candles=limit)

    candles = []
    for k in raw:
        # k: [time_s, open, high, low, close, vwap, volume, count]
        open_time_ms = int(k[0]) * 1000
        candles.append({
            "t": open_time_ms,
            "time": datetime.fromtimestamp(open_time_ms/1000, tz=timezone.utc).isoformat(),
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[6]),
        })

    return {"symbol": symbol, "interval": interval, "candles": candles}
