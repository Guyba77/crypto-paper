from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os

from ..routers.symbols import TOP20
from ..live.state import STATE, RunnerConfig
from ..live.runner import RUNNER

router = APIRouter()


def is_live_trading_enabled() -> bool:
    return os.environ.get("KRAKEN_TRADE_ENABLED", "false").lower() in ("1", "true", "yes")


class LiveStartRequest(BaseModel):
    symbols: List[str] = Field(default_factory=lambda: TOP20[:4])
    base_interval: str = "5m"
    trend_interval: str = "15m"

    strategy: str = "ema_cross"
    params: Dict[str, Any] = {}
    trade_mode: str = "off"  # off|paper|live_kraken


@router.get("/live/state")
async def live_state():
    return {
        "running": STATE.running,
        "started_at": STATE.started_at,
        "last_error": STATE.last_error,
        "config": STATE.config.__dict__ if STATE.config else None,
        "markets": {k: v.__dict__ for k, v in STATE.markets.items()},
    }


@router.post("/live/start")
async def live_start(req: LiveStartRequest):
    cfg = RunnerConfig(
        symbols=req.symbols,
        base_interval=req.base_interval,
        trend_interval=req.trend_interval,
        strategy=req.strategy,
        params=req.params,
        trade_mode=req.trade_mode,
        direction=str(req.params.get("direction", "both")),
    )
    await RUNNER.start(cfg)
    return {"ok": True, "running": STATE.running}


@router.post("/live/stop")
async def live_stop():
    await RUNNER.stop()
    return {"ok": True, "running": STATE.running}


@router.get("/live/logs")
async def live_logs(limit: int = 50):
    """Get recent execution logs."""
    logs = STATE.execution_logs[-limit:]
    return {
        "logs": [{"ts_ms": e.ts_ms, "level": e.level, "message": e.message} for e in logs],
        "total": len(STATE.execution_logs),
    }


@router.post("/live/logs/clear")
async def live_logs_clear():
    """Clear execution logs."""
    STATE.execution_logs.clear()
    return {"ok": True}


@router.get("/live/trade-enabled")
async def live_trade_enabled():
    """Check if live trading is enabled via env var."""
    return {
        "enabled": is_live_trading_enabled(),
        "current_mode": STATE.config.trade_mode if STATE.config else "off",
    }


class SetTradeModeRequest(BaseModel):
    mode: str = "off"  # off|paper|live_kraken


@router.post("/live/trade-mode")
async def set_trade_mode(req: SetTradeModeRequest):
    """Change trade mode on running screener."""
    if req.mode == "live_kraken" and not is_live_trading_enabled():
        return {
            "ok": False,
            "error": "Live trading disabled. Set KRAKEN_TRADE_ENABLED=true env var and restart backend.",
        }
    
    if STATE.config:
        STATE.config.trade_mode = req.mode
        STATE.log("info", f"Trade mode changed to: {req.mode}")
    
    return {
        "ok": True,
        "mode": STATE.config.trade_mode if STATE.config else "off",
    }


@router.get("/live/paper-trades")
async def paper_trades(limit: int = 50):
    """Get recent paper trades with P&L."""
    trades = STATE.paper_trades[-limit:]
    total_pnl = sum(t.pnl_quote for t in trades)
    wins = sum(1 for t in trades if t.pnl_quote >= 0)
    losses = len(trades) - wins
    
    return {
        "trades": [
            {
                "symbol": t.symbol,
                "side": t.side,
                "entry_price": t.entry_price,
                "entry_ts_ms": t.entry_ts_ms,
                "exit_price": t.exit_price,
                "exit_ts_ms": t.exit_ts_ms,
                "exit_reason": t.exit_reason,
                "pnl_pct": t.pnl_pct,
                "pnl_quote": t.pnl_quote,
                "size_quote": t.size_quote,
            }
            for t in trades
        ],
        "summary": {
            "total_trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / len(trades) * 100) if trades else 0,
            "total_pnl": total_pnl,
        },
    }


@router.get("/live/open-positions")
async def open_positions():
    """Get current open paper positions."""
    positions = []
    for sym, m in STATE.markets.items():
        if m.paper_position:
            pos = m.paper_position
            current = m.last_price or pos.entry_price
            if pos.side == "buy":
                unrealized_pct = ((current - pos.entry_price) / pos.entry_price) * 100
            else:
                unrealized_pct = ((pos.entry_price - current) / pos.entry_price) * 100
            unrealized_quote = pos.size_quote * (unrealized_pct / 100)
            
            positions.append({
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "entry_ts_ms": pos.entry_ts_ms,
                "stop": pos.stop,
                "tp": pos.tp,
                "size_quote": pos.size_quote,
                "current_price": current,
                "unrealized_pnl_pct": unrealized_pct,
                "unrealized_pnl_quote": unrealized_quote,
            })
    
    return {"positions": positions}
