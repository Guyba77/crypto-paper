from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from ..routers.symbols import TOP20
from ..live.state import STATE, RunnerConfig
from ..live.runner import RUNNER

router = APIRouter()


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
