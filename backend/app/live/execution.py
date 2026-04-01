from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Any, Dict, Optional

from .state import MarketState, RunnerConfig, now_ms, STATE, PaperPosition, PaperTrade

logger = logging.getLogger(__name__)


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
        ts = now_ms()
        price = m.last_price or 0.0
        
        # Get stop and TP from signal meta
        stop = m.signal_meta.get("stop")
        tp = m.signal_meta.get("tp")
        
        # Notional size (for P&L calculation)
        params = cfg.params or {}
        size_quote = float(params.get("paper_size", 100.0))
        
        # Create paper position
        position = PaperPosition(
            symbol=m.symbol,
            side=side,
            entry_price=price,
            entry_ts_ms=ts,
            stop=float(stop) if stop else None,
            tp=float(tp) if tp else None,
            size_quote=size_quote,
        )
        m.paper_position = position
        
        # Log entry
        stop_str = f"{stop:.2f}" if stop else "none"
        tp_str = f"{tp:.2f}" if tp else "none"
        log_msg = f"📝 PAPER {side.upper()} {m.symbol} @ {price:.2f} | Stop: {stop_str} | TP: {tp_str} | Size: ${size_quote:.0f}"
        logger.info(f"[PaperExecution] {log_msg}")
        STATE.log("info", log_msg)
        
        return {
            "mode": "paper",
            "side": side,
            "symbol": m.symbol,
            "price": price,
            "stop": stop,
            "tp": tp,
            "size_quote": size_quote,
            "ts_ms": ts,
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

        # Position sizing: 2% of quote asset balance (default USDT), or fallback to fixed amount
        quote_asset = str(params.get("quote_asset", "USDT"))
        position_pct = float(params.get("position_pct", 0.02))  # 2% default
        
        balance = client.get_asset_balance(quote_asset)
        log_msg = f"{quote_asset} balance: {balance:.2f}"
        logger.info(f"[KrakenExecution] {log_msg}")
        STATE.log("info", log_msg)
        
        if balance > 0:
            quote_amount = balance * position_pct
            log_msg = f"Position size: {position_pct*100:.1f}% of {balance:.2f} = {quote_amount:.2f} {quote_asset}"
            logger.info(f"[KrakenExecution] {log_msg}")
            STATE.log("info", log_msg)
        else:
            # Fallback to fixed amount if balance fetch fails or is zero
            quote_amount = float(params.get("order_quote", 50.0))
            log_msg = f"No {quote_asset} balance found, using fallback: {quote_amount:.2f}"
            logger.warning(f"[KrakenExecution] {log_msg}")
            STATE.log("warn", log_msg)
        
        if not m.last_price or m.last_price <= 0:
            raise RuntimeError("Missing last_price; cannot size order.")
        volume = quote_amount / float(m.last_price)
        log_msg = f"{side.upper()} {pair}: {volume:.8f} @ ~{m.last_price:.2f} (quote: {quote_amount:.2f} {quote_asset})"
        logger.info(f"[KrakenExecution] {log_msg}")
        STATE.log("info", log_msg)

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


def check_paper_exit(m: MarketState, high: float, low: float) -> bool:
    """Check if paper position should be closed. Returns True if exited."""
    pos = m.paper_position
    if not pos:
        return False
    
    price = m.last_price or 0.0
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    
    if pos.side == "buy":
        # Long position: stop if low <= stop, TP if high >= tp
        if pos.stop and low <= pos.stop:
            exit_price = pos.stop
            exit_reason = "stop"
        elif pos.tp and high >= pos.tp:
            exit_price = pos.tp
            exit_reason = "tp"
    else:
        # Short position: stop if high >= stop, TP if low <= tp
        if pos.stop and high >= pos.stop:
            exit_price = pos.stop
            exit_reason = "stop"
        elif pos.tp and low <= pos.tp:
            exit_price = pos.tp
            exit_reason = "tp"
    
    if exit_price and exit_reason:
        ts = now_ms()
        
        # Calculate P&L
        if pos.side == "buy":
            pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
        else:
            pnl_pct = ((pos.entry_price - exit_price) / pos.entry_price) * 100
        
        pnl_quote = pos.size_quote * (pnl_pct / 100)
        
        # Record the trade
        trade = PaperTrade(
            symbol=pos.symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            entry_ts_ms=pos.entry_ts_ms,
            exit_price=exit_price,
            exit_ts_ms=ts,
            exit_reason=exit_reason,
            pnl_pct=pnl_pct,
            pnl_quote=pnl_quote,
            size_quote=pos.size_quote,
        )
        STATE.record_paper_trade(trade)
        
        # Log exit
        emoji = "✅" if pnl_pct >= 0 else "❌"
        reason_emoji = "🛑" if exit_reason == "stop" else "🎯"
        log_msg = f"{emoji} PAPER CLOSE {pos.symbol} @ {exit_price:.2f} | {reason_emoji} {exit_reason.upper()} | P&L: {pnl_pct:+.2f}% (${pnl_quote:+.2f})"
        logger.info(f"[PaperExecution] {log_msg}")
        STATE.log("info" if pnl_pct >= 0 else "warn", log_msg)
        
        # Clear position
        m.paper_position = None
        m.in_position = False
        
        return True
    
    return False
