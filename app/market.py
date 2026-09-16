from __future__ import annotations

from functools import lru_cache
import ccxt


@lru_cache(maxsize=1)
def exchange():
    klass = getattr(ccxt, "htx", None) or getattr(ccxt, "huobi")
    return klass({"enableRateLimit": True, "options": {"defaultType": "swap"}})


def fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict]:
    rows = exchange().fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return [
        {"ts_ms": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
        for r in rows
    ]


def symbols() -> list[str]:
    ex = exchange()
    markets = ex.load_markets()
    out = []
    for sym, m in markets.items():
        if m.get("swap") and m.get("linear") and m.get("quote") == "USDT" and m.get("active", True):
            out.append(sym)
    preferred = ["ETH/USDT:USDT", "BTC/USDT:USDT", "DOGE/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"]
    ordered = [s for s in preferred if s in out] + sorted(s for s in out if s not in preferred)
    return ordered[:250]
