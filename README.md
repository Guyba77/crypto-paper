# Crypto Paper Trading + Backtesting (3m candles)

MVP web app for Binance spot top-20 symbols:
- ingest/store 3-minute OHLCV
- run built-in strategy backtests (parameterized)
- paper trading via replay / periodic updates

## Repo layout
- `backend/` FastAPI + backtest engine
- `frontend/` Next.js web UI
- `docker-compose.yml` Postgres + Redis

## Quickstart
1) `docker compose up -d`
2) Backend:
   - `cd backend && python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`
   - `uvicorn app.main:app --reload --port 8000`
3) Frontend:
   - `cd frontend && npm i`
   - `npm run dev`

Then open http://localhost:3000
