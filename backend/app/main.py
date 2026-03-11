from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, symbols, candles, backtest, batch, live

app = FastAPI(title="crypto-paper", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(symbols.router, prefix="/api")
app.include_router(candles.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(batch.router, prefix="/api")
app.include_router(live.router, prefix="/api")
