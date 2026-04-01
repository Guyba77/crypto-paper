from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal, Any
import time


Direction = Literal["long", "short", "both"]
TradeMode = Literal["off", "paper", "live_kraken"]


@dataclass
class PaperPosition:
    symbol: str
    side: str  # 'buy' or 'sell'
    entry_price: float
    entry_ts_ms: int
    stop: Optional[float] = None
    tp: Optional[float] = None
    size_quote: float = 100.0  # notional size in quote currency


@dataclass
class PaperTrade:
    symbol: str
    side: str
    entry_price: float
    entry_ts_ms: int
    exit_price: float
    exit_ts_ms: int
    exit_reason: str  # 'stop' | 'tp' | 'manual'
    pnl_pct: float
    pnl_quote: float
    size_quote: float


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
    
    # paper trading position
    paper_position: Optional[PaperPosition] = None


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
class LogEntry:
    ts_ms: int
    level: str  # 'info' | 'warn' | 'error'
    message: str


@dataclass
class RunnerState:
    running: bool = False
    started_at: Optional[float] = None
    markets: Dict[str, MarketState] = field(default_factory=dict)
    last_error: Optional[str] = None
    config: Optional[RunnerConfig] = None
    execution_logs: List[LogEntry] = field(default_factory=list)
    max_logs: int = 100  # keep last N logs
    paper_trades: List[PaperTrade] = field(default_factory=list)
    max_paper_trades: int = 100

    def log(self, level: str, message: str):
        entry = LogEntry(ts_ms=now_ms(), level=level, message=message)
        self.execution_logs.append(entry)
        # Trim old logs
        if len(self.execution_logs) > self.max_logs:
            self.execution_logs = self.execution_logs[-self.max_logs:]

    def record_paper_trade(self, trade: PaperTrade):
        self.paper_trades.append(trade)
        if len(self.paper_trades) > self.max_paper_trades:
            self.paper_trades = self.paper_trades[-self.max_paper_trades:]


STATE = RunnerState()


def now_ms() -> int:
    return int(time.time() * 1000)
