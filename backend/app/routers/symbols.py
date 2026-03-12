from fastapi import APIRouter

router = APIRouter()

# MVP: fixed Kraken USD universe (can be made dynamic later)
# Use Kraken WS pair names (e.g. XBT/USD)
TOP20 = [
    "XBT/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "ADA/USD",
    "DOT/USD",
    "LINK/USD",
    "LTC/USD",
    "BCH/USD",
    "XLM/USD",
    "ATOM/USD",
    "UNI/USD",
    "ETC/USD",
    "TRX/USD",
    "DOGE/USD",
    "AVAX/USD",
    "MATIC/USD",
]

@router.get("/symbols")
def list_symbols():
    return {"exchange": "kraken", "symbols": TOP20}
