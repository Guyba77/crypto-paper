from fastapi import APIRouter

router = APIRouter()

# MVP: fixed top-20 universe (can be made dynamic later)
TOP20 = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "ADAUSDT","DOGEUSDT","TRXUSDT","AVAXUSDT","LINKUSDT",
    "DOTUSDT","MATICUSDT","TONUSDT","SHIBUSDT","LTCUSDT",
    "BCHUSDT","UNIUSDT","ATOMUSDT","XLMUSDT","ETCUSDT",
]

@router.get("/symbols")
def list_symbols():
    return {"exchange": "binance", "symbols": TOP20}
