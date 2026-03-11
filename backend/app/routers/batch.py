from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Any, Dict

from .backtest import BacktestRequest, run_backtest

router = APIRouter()


class BatchBacktestRequest(BaseModel):
    symbols: List[str] = Field(min_length=1)
    backtest: BacktestRequest


@router.post("/backtest/batch")
async def run_batch(req: BatchBacktestRequest):
    results: List[Dict[str, Any]] = []
    for sym in req.symbols:
        bt = req.backtest.model_copy(update={"symbol": sym})
        r = await run_backtest(bt)
        results.append(r)

    # sort by return_pct if present
    def key_fn(x: Dict[str, Any]):
        try:
            return float(x.get("stats", {}).get("return_pct"))
        except Exception:
            return float("-inf")

    results_sorted = sorted(results, key=key_fn, reverse=True)
    return {"count": len(results_sorted), "results": results_sorted}
