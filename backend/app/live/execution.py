from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Dict, Optional

from .state import MarketState, RunnerConfig, now_ms


def _kraken_trade_pair(pair: str) -> str:
    """Normalize a Kraken WS-style pair like 'XBT/USD' to trade pair code.

    For private REST AddOrder, Kraken generally accepts codes without '/'.
    """
    return pair.upper().replace("/", "")


class ExecutionEngine:
    async def on_entry(self, m: MarketState, cfg: RunnerConfig, side: str) -> Dict[str, Any]:
        raise NotImplementedError


class PaperExecution(ExecutionEngine):
    async def on_entry(self, m: MarketState, cfg: RunnerConfig, side: str) -> Dict[str, Any]:
        # Paper execution just marks the market as "in position".
        return {
            "mode": "paper",
            "side": side,
            "symbol": m.symbol,
            "price": m.last_price,
            "ts_ms": now_ms(),
        }


class KrakenExecution(ExecutionEngine):
    async def on_entry(self, m: MarketState, cfg: RunnerConfig, side: str) -> Dict[str, Any]:
        # Hard safety gate so we don't accidentally place real orders.
        enabled = os.environ.get("KRAKEN_TRADE_ENABLED", "false").lower() in ("1", "true", "yes")
        if not enabled:
            raise RuntimeError("Kraken execution disabled. Set KRAKEN_TRADE_ENABLED=true to allow live orders.")

        from ..services.kraken import KrakenClient

        params = cfg.params or {}
        pairs = params.get("kraken_pairs") or {}
        # m.symbol is now expected to be a Kraken WS pair like 'XBT/USD'
        if isinstance(pairs, dict) and m.symbol in pairs:
            pair = str(pairs[m.symbol])
        else:
            pair = _kraken_trade_pair(m.symbol)

        # Kraken spot doesn't support true shorting without margin; keep MVP safe.
        if side == "sell":
            raise RuntimeError("Short/SELL entry not supported for Kraken spot execution in MVP.")

        quote_amount = float(params.get("order_quote", 50.0))
        if not m.last_price or m.last_price <= 0:
            raise RuntimeError("Missing last_price; cannot size order.")
        volume = quote_amount / float(m.last_price)

        client = KrakenClient.from_env()
        res = client.add_order(pair=pair, side=side, volume=volume, ordertype="market", validate=False)
        return {
            "mode": "live_kraken",
            "pair": pair,
            "side": side,
            "quote_amount": quote_amount,
            "volume": volume,
            "raw": res,
        }


def get_execution_engine(cfg: RunnerConfig) -> Optional[ExecutionEngine]:
    if cfg.trade_mode == "paper":
        return PaperExecution()
    if cfg.trade_mode == "live_kraken":
        return KrakenExecution()
    return None
