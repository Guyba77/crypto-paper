from fastapi import APIRouter, Query
from datetime import datetime, timezone

from ..services.binance import fetch_klines

router = APIRouter()

@router.get("/candles")
async def get_candles(
    symbol: str,
    interval: str = Query(default="3m"),
    limit: int = Query(default=500, ge=1, le=1000),
):
    # MVP: proxy to Binance. Next step: persist to DB and serve from there.
    raw = await fetch_klines(symbol=symbol, interval=interval, limit=limit)

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
