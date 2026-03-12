from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import time
import requests


def interval_to_minutes(interval: str) -> int:
    """Convert UI interval strings like '5m', '15m', '1h', '4h', '1d' to Kraken minutes."""
    s = interval.strip().lower()
    if s.endswith("m"):
        return int(s[:-1])
    if s.endswith("h"):
        return int(s[:-1]) * 60
    if s.endswith("d"):
        return int(s[:-1]) * 60 * 24
    # allow raw minutes
    return int(s)


def _normalize_pair(pair: str) -> str:
    """Accept Kraken WS-style pairs like 'XBT/USD' and convert to REST codes.

    Kraken public REST endpoints typically accept codes without '/'.
    """
    return pair.strip().upper().replace("/", "")


def fetch_ohlc_paged(
    pair: str,
    interval: str,
    max_candles: int = 500,
    since_ms: Optional[int] = None,
    base_url: str = "https://api.kraken.com",
) -> List[List[Any]]:
    """Fetch up to max_candles OHLC rows for a Kraken pair.

    Returns Kraken OHLC rows in the original Kraken format:
      [time, open, high, low, close, vwap, volume, count]
    where time is seconds since epoch.

    Paging:
      Kraken supports a 'since' (seconds) parameter and returns 'last'.
      We iterate forward until we have enough candles or no progress.
    """

    minutes = interval_to_minutes(interval)
    url = base_url.rstrip("/") + "/0/public/OHLC"

    pair_code = _normalize_pair(pair)

    out: List[List[Any]] = []
    since_s: Optional[int] = int(since_ms / 1000) if since_ms is not None else None

    # Hard cap loops to avoid infinite paging
    loops = 0
    while len(out) < max_candles and loops < 50:
        loops += 1
        params: Dict[str, Any] = {"pair": pair_code, "interval": minutes}
        if since_s is not None:
            params["since"] = since_s

        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        errs = data.get("error") or []
        if errs:
            raise RuntimeError(f"Kraken OHLC error: {errs}")

        result = data.get("result") or {}
        last = result.get("last")

        # The result key for OHLC is not stable (it can be an internal pair id).
        rows: Optional[List[List[Any]]] = None
        for k, v in result.items():
            if k == "last":
                continue
            if isinstance(v, list):
                rows = v
                break

        if not rows:
            break

        # Append rows; de-dupe by timestamp
        for row in rows:
            if len(out) >= max_candles:
                break
            out.append(row)

        # Progress the cursor
        if last is None:
            break
        next_since_s = int(last)
        if since_s is not None and next_since_s <= since_s:
            break
        since_s = next_since_s

        # Be nice to the API
        time.sleep(0.05)

    # Kraken may include earlier candles again around the 'since' boundary; sort/dedupe.
    seen = set()
    deduped: List[List[Any]] = []
    for row in sorted(out, key=lambda x: int(x[0])):
        ts = int(row[0])
        if ts in seen:
            continue
        seen.add(ts)
        deduped.append(row)

    return deduped[-max_candles:]
