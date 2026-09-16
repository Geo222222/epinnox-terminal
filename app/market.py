from __future__ import annotations

from functools import lru_cache
import ccxt


@lru_cache(maxsize=1)
def exchange():
    klass = getattr(ccxt, "htx", None) or getattr(ccxt, "huobi")
    return klass({"enableRateLimit": True, "options": {"defaultType": "swap"}})


def _rows_to_candles(rows) -> list[dict]:
    return [
        {"ts_ms": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
        for r in rows
    ]


def fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict]:
    rows = exchange().fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return _rows_to_candles(rows)


def fetch_ohlcv_range(
    symbol: str,
    timeframe: str,
    start_ts_ms: int,
    end_ts_ms: int,
    max_bars: int = 50000,
) -> list[dict]:
    """Page HTX OHLCV forward so a TradingView date window can be reproduced."""
    if start_ts_ms >= end_ts_ms:
        raise ValueError("start_ts_ms must be before end_ts_ms")
    tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000}[timeframe]
    ex = exchange()
    since = int(start_ts_ms)
    out: list[dict] = []
    seen: set[int] = set()

    while since <= end_ts_ms and len(out) < max_bars:
        batch_size = min(1000, max_bars - len(out))
        rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=batch_size)
        if not rows:
            break
        advanced = False
        for candle in _rows_to_candles(rows):
            ts = candle["ts_ms"]
            if ts > end_ts_ms:
                break
            if ts >= start_ts_ms and ts not in seen:
                out.append(candle)
                seen.add(ts)
            if ts >= since:
                since = ts + tf_ms
                advanced = True
        if not advanced:
            break
        if rows[-1][0] > end_ts_ms:
            break

    out.sort(key=lambda x: x["ts_ms"])
    return out


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
