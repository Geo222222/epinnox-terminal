from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import threading
import time
from typing import Any

import ccxt


TIMEFRAME_SPECS: dict[str, dict[str, int | str | bool]] = {
    "1m": {"source": "1m", "factor": 1, "ms": 60_000},
    "5m": {"source": "5m", "factor": 1, "ms": 300_000},
    "15m": {"source": "15m", "factor": 1, "ms": 900_000},
    "30m": {"source": "30m", "factor": 1, "ms": 1_800_000},
    "1h": {"source": "1h", "factor": 1, "ms": 3_600_000},
    "2h": {"source": "1h", "factor": 2, "ms": 7_200_000},
    "3h": {"source": "1h", "factor": 3, "ms": 10_800_000},
    "4h": {"source": "4h", "factor": 1, "ms": 14_400_000},
    "5h": {"source": "1h", "factor": 5, "ms": 18_000_000},
    "8h": {"source": "4h", "factor": 2, "ms": 28_800_000},
    "1d": {"source": "1d", "factor": 1, "ms": 86_400_000},
    "5d": {"source": "1d", "factor": 5, "ms": 432_000_000},
    "1w": {"source": "1w", "factor": 1, "ms": 604_800_000},
    "1M": {"source": "1d", "factor": 31, "ms": 2_592_000_000, "calendar_month": True},
}

_CACHE_LOCK = threading.RLock()
_EXCHANGE_LOCK = threading.RLock()
_CACHE: dict[tuple[Any, ...], tuple[float, list[dict]]] = {}
_CACHE_MAX = 256
LATEST_TTL_SECONDS = 5.0
RANGE_TTL_SECONDS = 300.0


@lru_cache(maxsize=1)
def exchange():
    klass = getattr(ccxt, "htx", None) or getattr(ccxt, "huobi")
    return klass({"enableRateLimit": True, "options": {"defaultType": "swap"}})


def _fetch_exchange_ohlcv(*args, **kwargs):
    with _EXCHANGE_LOCK:
        return exchange().fetch_ohlcv(*args, **kwargs)


def timeframe_ms(timeframe: str) -> int:
    try:
        return int(TIMEFRAME_SPECS[timeframe]["ms"])
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe}") from exc


def _copy_candles(rows: list[dict]) -> list[dict]:
    return [dict(row) for row in rows]


def _cache_get(key: tuple[Any, ...], ttl_seconds: float) -> list[dict] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        stored_at, rows = item
        if now - stored_at > ttl_seconds:
            _CACHE.pop(key, None)
            return None
        return _copy_candles(rows)


def _cache_put(key: tuple[Any, ...], rows: list[dict]) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            oldest = min(_CACHE.items(), key=lambda item: item[1][0])[0]
            _CACHE.pop(oldest, None)
        _CACHE[key] = (time.monotonic(), _copy_candles(rows))


def cache_stats() -> dict[str, int]:
    with _CACHE_LOCK:
        return {"entries": len(_CACHE), "max_entries": _CACHE_MAX}


def clear_market_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _rows_to_candles(rows) -> list[dict]:
    return [
        {"ts_ms": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
        for r in rows
    ]


def _bucket_key(ts_ms: int, timeframe: str):
    spec = TIMEFRAME_SPECS[timeframe]
    if spec.get("calendar_month"):
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        return (dt.year, dt.month)
    width = int(spec["ms"])
    return ts_ms // width


def _bucket_start(key, timeframe: str) -> int:
    spec = TIMEFRAME_SPECS[timeframe]
    if spec.get("calendar_month"):
        year, month = key
        return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return int(key) * int(spec["ms"])


def _aggregate(rows: list[dict], timeframe: str) -> list[dict]:
    spec = TIMEFRAME_SPECS[timeframe]
    if int(spec.get("factor", 1)) == 1 and not spec.get("calendar_month"):
        return rows
    out: list[dict] = []
    current_key = None
    bucket = None
    for row in rows:
        key = _bucket_key(int(row["ts_ms"]), timeframe)
        if key != current_key:
            if bucket is not None:
                out.append(bucket)
            current_key = key
            bucket = {
                "ts_ms": _bucket_start(key, timeframe),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        else:
            bucket["high"] = max(float(bucket["high"]), float(row["high"]))
            bucket["low"] = min(float(bucket["low"]), float(row["low"]))
            bucket["close"] = float(row["close"])
            bucket["volume"] = float(bucket["volume"]) + float(row["volume"])
    if bucket is not None:
        out.append(bucket)
    return out


def _source_spec(timeframe: str) -> tuple[str, int]:
    if timeframe not in TIMEFRAME_SPECS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    source = str(TIMEFRAME_SPECS[timeframe]["source"])
    source_ms = timeframe_ms(source) if source in TIMEFRAME_SPECS else {
        "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
        "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000,
    }[source]
    return source, source_ms


def _fetch_raw_range(symbol: str, source: str, source_ms: int, start_ts_ms: int, end_ts_ms: int, max_bars: int) -> list[dict]:
    since = int(start_ts_ms)
    out: list[dict] = []
    seen: set[int] = set()
    while since <= end_ts_ms and len(out) < max_bars:
        batch_size = min(1000, max_bars - len(out))
        rows = _fetch_exchange_ohlcv(symbol, timeframe=source, since=since, limit=batch_size)
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
                since = ts + source_ms
                advanced = True
        if not advanced or int(rows[-1][0]) > end_ts_ms:
            break
    out.sort(key=lambda x: x["ts_ms"])
    return out


def fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict]:
    if timeframe not in TIMEFRAME_SPECS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    key = ("latest", symbol, timeframe, int(limit))
    cached = _cache_get(key, LATEST_TTL_SECONDS)
    if cached is not None:
        return cached

    spec = TIMEFRAME_SPECS[timeframe]
    factor = int(spec.get("factor", 1))
    if factor == 1 and not spec.get("calendar_month"):
        rows = _fetch_exchange_ohlcv(symbol, timeframe=str(spec["source"]), limit=limit)
        out = _rows_to_candles(rows)
    else:
        end = int(time.time() * 1000)
        width = timeframe_ms(timeframe)
        start = end - (max(1, limit) + 2) * width
        out = fetch_ohlcv_range(symbol, timeframe, start, end, max_bars=max(limit + 2, 100))[-limit:]
    _cache_put(key, out)
    return _copy_candles(out)


def fetch_ohlcv_range(
    symbol: str,
    timeframe: str,
    start_ts_ms: int,
    end_ts_ms: int,
    max_bars: int = 50000,
) -> list[dict]:
    """Page HTX OHLCV forward and aggregate custom TradingView-style intervals."""
    if start_ts_ms >= end_ts_ms:
        raise ValueError("start_ts_ms must be before end_ts_ms")
    if timeframe not in TIMEFRAME_SPECS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    key = ("range", symbol, timeframe, int(start_ts_ms), int(end_ts_ms), int(max_bars))
    cached = _cache_get(key, RANGE_TTL_SECONDS)
    if cached is not None:
        return cached

    source, source_ms = _source_spec(timeframe)
    spec = TIMEFRAME_SPECS[timeframe]
    factor = int(spec.get("factor", 1))
    source_cap = min(250_000, max_bars * max(1, factor) + max(100, factor * 4))
    raw = _fetch_raw_range(symbol, source, source_ms, start_ts_ms - source_ms * factor, end_ts_ms, source_cap)
    out = _aggregate(raw, timeframe)
    out = [row for row in out if start_ts_ms <= int(row["ts_ms"]) <= end_ts_ms][:max_bars]
    _cache_put(key, out)
    return _copy_candles(out)


def _eligible_markets() -> tuple[dict[str, dict[str, Any]], list[str]]:
    with _EXCHANGE_LOCK:
        markets = exchange().load_markets()
    eligible: dict[str, dict[str, Any]] = {}
    for sym, market in markets.items():
        if market.get("swap") and market.get("linear") and market.get("quote") == "USDT" and market.get("active", True):
            eligible[sym] = market
    preferred = ["ETH/USDT:USDT", "BTC/USDT:USDT", "DOGE/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"]
    ordered = [s for s in preferred if s in eligible] + sorted(s for s in eligible if s not in preferred)
    return eligible, ordered


def symbols() -> list[str]:
    return _eligible_markets()[1]


def market_catalog() -> list[dict[str, Any]]:
    """Return the complete active HTX linear-USDT swap catalog in one bulk request.

    The live Universe consumes this catalog directly. Missing ticker fields are
    represented as ``None`` rather than fabricated values so degraded HTX data
    remains visible and fail-closed. No arbitrary top-N cap is applied to the
    eligible venue catalog.
    """
    eligible, ordered = _eligible_markets()
    with _EXCHANGE_LOCK:
        client = exchange()
        tickers = client.fetch_tickers(ordered) if client.has.get("fetchTickers") else {}
    now = int(time.time() * 1000)
    rows: list[dict[str, Any]] = []
    for symbol in ordered:
        market = eligible[symbol]
        ticker = tickers.get(symbol) or {}
        info = ticker.get("info") if isinstance(ticker.get("info"), dict) else {}
        last = ticker.get("last")
        quote_volume = ticker.get("quoteVolume")
        base_volume = ticker.get("baseVolume")
        percentage = ticker.get("percentage")
        change = ticker.get("change")
        if percentage is None and change is not None and ticker.get("open"):
            try:
                percentage = float(change) / float(ticker["open"]) * 100.0
            except (TypeError, ValueError, ZeroDivisionError):
                percentage = None
        rows.append({
            "symbol": symbol,
            "base": str(market.get("base") or symbol.split("/")[0]),
            "quote": "USDT",
            "market_id": market.get("id"),
            "active": bool(market.get("active", True)),
            "contract_size": market.get("contractSize"),
            "price": None if last is None else float(last),
            "change_24h_pct": None if percentage is None else float(percentage),
            "base_volume_24h": None if base_volume is None else float(base_volume),
            "quote_volume_24h": None if quote_volume is None else float(quote_volume),
            "bid": None if ticker.get("bid") is None else float(ticker["bid"]),
            "ask": None if ticker.get("ask") is None else float(ticker["ask"]),
            "high_24h": None if ticker.get("high") is None else float(ticker["high"]),
            "low_24h": None if ticker.get("low") is None else float(ticker["low"]),
            "ticker_ts_ms": int(ticker.get("timestamp") or now),
            "funding_rate": _safe_float(info.get("funding_rate") or info.get("fundingRate")),
            "open_interest": _safe_float(info.get("open_interest") or info.get("openInterest")),
        })
    return rows


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None