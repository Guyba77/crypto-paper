from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal, Any
import time


Direction = Literal["long", "short", "both"]
TradeMode = Literal["off", "paper", "live_kraken"]


@dataclass
class MarketState:
    symbol: str
    last_update_ms: Optional[int] = None
    last_price: Optional[float] = None
    trend_ma: Optional[float] = None
    signal: Optional[str] = None  # 'enter_long'|'enter_short'|None
    signal_meta: Dict[str, Any] = field(default_factory=dict)

    # execution state (very lightweight)
    in_position: bool = False
    last_exec_ms: Optional[int] = None
    last_exec_error: Optional[str] = None
    last_order: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunnerConfig:
    symbols: List[str]
    base_interval: str = "5m"
    trend_interval: str = "15m"
    days_seed: int = 10

    strategy: str = "ema_cross"
    params: Dict[str, Any] = field(default_factory=dict)

    trade_mode: TradeMode = "off"
    direction: Direction = "both"


@dataclass
class RunnerState:
    running: bool = False
    started_at: Optional[float] = None
    markets: Dict[str, MarketState] = field(default_factory=dict)
    last_error: Optional[str] = None
    config: Optional[RunnerConfig] = None


STATE = RunnerState()


def now_ms() -> int:
    return int(time.time() * 1000)
