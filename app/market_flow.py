from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .market import _EXCHANGE_LOCK, exchange
from .storage import DB_PATH

VENUE = "HTX"
USD_QUOTES = {"USD", "USDT", "USDC", "FDUSD", "TUSD", "DAI"}
WINDOW_MS = {
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "24h": 24 * 60 * 60_000,
}
SESSION_SPECS = {
    "ASIA": ("Asia/Singapore", 9, 17),
    "LONDON": ("Europe/London", 8, 16),
    "NEW_YORK": ("America/New_York", 9, 17),
}


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start_ms: int
    end_ms: int
    active: bool


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1.0) * 100.0


def _percentile_rank(samples: list[float], value: float) -> float | None:
    samples = sorted(x for x in samples if math.isfinite(x))
    if len(samples) < 8:
        return None
    below = sum(1 for x in samples if x < value)
    equal = sum(1 for x in samples if x == value)
    return 100.0 * (below + 0.5 * equal) / len(samples)


def participation_state(percentile: float | None) -> str:
    if percentile is None:
        return "WARMING"
    if percentile < 25:
        return "DORMANT"
    if percentile < 65:
        return "NORMAL"
    if percentile < 80:
        return "ACTIVE"
    if percentile < 90:
        return "ELEVATED"
    if percentile <= 97:
        return "HIGH_PARTICIPATION"
    return "EXTREME"


def flow_price_state(price_change_pct: float | None, relative_flow: float | None) -> str:
    if price_change_pct is None or relative_flow is None:
        return "INSUFFICIENT_EVIDENCE"
    flow_up = relative_flow >= 1.25
    flow_down = relative_flow <= 0.75
    flat_price = abs(price_change_pct) < 0.35
    if flat_price and flow_up:
        return "COMPRESSION_POSITIONING"
    if price_change_pct > 0 and flow_up:
        return "EXPANSION"
    if price_change_pct < 0 and flow_up:
        return "DISTRIBUTION_SELL_PRESSURE"
    if price_change_pct > 0 and flow_down:
        return "LOW_CONVICTION_ADVANCE"
    if price_change_pct < 0 and flow_down:
        return "LOW_PARTICIPATION_DECLINE"
    return "BALANCED"


def oi_context(price_change_pct: float | None, flow_up: bool, oi_change_pct: float | None) -> str:
    if price_change_pct is None or oi_change_pct is None or not flow_up:
        return "INSUFFICIENT_EVIDENCE"
    if price_change_pct > 0 and oi_change_pct > 0:
        return "NEW_POSITIONING_EXPANSION"
    if price_change_pct > 0 and oi_change_pct < 0:
        return "SHORT_COVERING_POSSIBILITY"
    if price_change_pct < 0 and oi_change_pct > 0:
        return "NEW_SHORT_POSITIONING_POSSIBILITY"
    if price_change_pct < 0 and oi_change_pct < 0:
        return "LONG_LIQUIDATION_DERISKING_POSSIBILITY"
    return "BALANCED"


def session_window(name: str, now_ms: int | None = None) -> SessionWindow:
    now_utc = datetime.fromtimestamp((now_ms or int(time.time() * 1000)) / 1000.0, tz=timezone.utc)
    tz_name, start_hour, end_hour = SESSION_SPECS[name]
    tz = ZoneInfo(tz_name)
    local = now_utc.astimezone(tz)
    start = local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = local.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if local < start:
        start -= timedelta(days=1)
        end -= timedelta(days=1)
    active = start <= local < end
    if local >= end:
        active = False
    return SessionWindow(
        name=name,
        start_ms=int(start.astimezone(timezone.utc).timestamp() * 1000),
        end_ms=int(end.astimezone(timezone.utc).timestamp() * 1000),
        active=active,
    )


class MarketFlowEngine:
    """Canonical asset-flow state for the live Universe.

    HTX's 24h venue ticker notional is used as the immediate venue-level truth.
    Shorter rolling/session windows are built from normalized recent trade events
    captured by the background collector. Coverage and feed quality are exposed so
    the UI never presents an incomplete REST sample as complete global flow.
    """

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._catalog_supplier: Callable[[], list[dict[str, Any]]] | None = None
        self._runtime_started_ms = int(time.time() * 1000)
        self._cursors: dict[str, int] = {}
        self._spot_24h: dict[str, float] = {}
        self._spot_updated_ms = 0
        self._oi_history: dict[str, deque[tuple[int, float]]] = {}
        self._price_history: dict[str, deque[tuple[int, float]]] = {}
        self._feed_error: str | None = None
        self._feed_state = "STARTING"
        self._last_trade_ms = 0
        self._round_robin = 0
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_flow_minute (
                    venue TEXT NOT NULL,
                    canonical_asset TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    minute_ms INTEGER NOT NULL,
                    notional_usd REAL NOT NULL DEFAULT 0,
                    buy_notional_usd REAL NOT NULL DEFAULT 0,
                    sell_notional_usd REAL NOT NULL DEFAULT 0,
                    trade_count INTEGER NOT NULL DEFAULT 0,
                    last_price REAL,
                    PRIMARY KEY(venue, canonical_asset, instrument_type, minute_ms)
                );
                CREATE INDEX IF NOT EXISTS idx_market_flow_asset_time
                  ON market_flow_minute(canonical_asset, minute_ms);
                """
            )

    def start(self, catalog_supplier: Callable[[], list[dict[str, Any]]]) -> None:
        with self._lock:
            self._catalog_supplier = catalog_supplier
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._runtime_started_ms = int(time.time() * 1000)
            self._thread = threading.Thread(target=self._loop, name="epinnox-market-flow", daemon=True)
            self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def observe_catalog(self, catalog: list[dict[str, Any]]) -> None:
        now = int(time.time() * 1000)
        with self._lock:
            for row in catalog:
                asset = str(row.get("base") or "").upper()
                price = _safe_float(row.get("price"))
                oi = _safe_float(row.get("open_interest"))
                if asset and price is not None:
                    history = self._price_history.setdefault(asset, deque(maxlen=5000))
                    history.append((now, price))
                if asset and oi is not None:
                    history = self._oi_history.setdefault(asset, deque(maxlen=5000))
                    history.append((now, oi))
            cutoff = now - 9 * 60 * 60_000
            for histories in (self._price_history, self._oi_history):
                for history in histories.values():
                    while history and history[0][0] < cutoff:
                        history.popleft()

    def _loop(self) -> None:
        while not self._stop.is_set():
            supplier = self._catalog_supplier
            catalog = supplier() if supplier else []
            if not catalog:
                with self._lock:
                    self._feed_state = "WAITING"
                self._stop.wait(1.0)
                continue
            try:
                now = int(time.time() * 1000)
                if now - self._spot_updated_ms >= 30_000:
                    self._refresh_spot_notional(catalog)
                ordered = sorted(catalog, key=lambda row: float(row.get("quote_volume_24h") or 0.0), reverse=True)
                if ordered:
                    row = ordered[self._round_robin % len(ordered)]
                    self._round_robin += 1
                    self._collect_recent_trades(row)
                with self._lock:
                    self._feed_state = "RUNNING"
                    self._feed_error = None
            except Exception as exc:
                with self._lock:
                    self._feed_state = "DEGRADED"
                    self._feed_error = str(exc)
            self._stop.wait(0.25)

    def _collect_recent_trades(self, market: dict[str, Any]) -> None:
        symbol = str(market.get("symbol") or "")
        asset = str(market.get("base") or "").upper()
        if not symbol or not asset:
            return
        now = int(time.time() * 1000)
        cursor = self._cursors.get(symbol, max(self._runtime_started_ms, now - 15 * 60_000))
        with _EXCHANGE_LOCK:
            client = exchange()
            if not client.has.get("fetchTrades"):
                self._feed_state = "TICKER_ONLY"
                return
            trades = client.fetch_trades(symbol, since=cursor, limit=1000)
        if not trades:
            return
        rows: dict[int, dict[str, float | int | None]] = {}
        newest = cursor
        for trade in trades:
            ts = int(trade.get("timestamp") or 0)
            if ts <= 0:
                continue
            newest = max(newest, ts + 1)
            price = _safe_float(trade.get("price"))
            amount = _safe_float(trade.get("amount"))
            if price is None or amount is None or price <= 0 or amount <= 0:
                continue
            notional = price * amount
            minute = ts - ts % 60_000
            bucket = rows.setdefault(minute, {"notional": 0.0, "buy": 0.0, "sell": 0.0, "count": 0, "price": price})
            bucket["notional"] = float(bucket["notional"] or 0) + notional
            side = str(trade.get("side") or "").lower()
            if side == "buy":
                bucket["buy"] = float(bucket["buy"] or 0) + notional
            elif side == "sell":
                bucket["sell"] = float(bucket["sell"] or 0) + notional
            bucket["count"] = int(bucket["count"] or 0) + 1
            bucket["price"] = price
        if rows:
            with self._connect() as conn:
                for minute, bucket in rows.items():
                    conn.execute(
                        """INSERT INTO market_flow_minute(
                             venue,canonical_asset,instrument_type,minute_ms,notional_usd,
                             buy_notional_usd,sell_notional_usd,trade_count,last_price)
                           VALUES(?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(venue,canonical_asset,instrument_type,minute_ms) DO UPDATE SET
                             notional_usd=market_flow_minute.notional_usd+excluded.notional_usd,
                             buy_notional_usd=market_flow_minute.buy_notional_usd+excluded.buy_notional_usd,
                             sell_notional_usd=market_flow_minute.sell_notional_usd+excluded.sell_notional_usd,
                             trade_count=market_flow_minute.trade_count+excluded.trade_count,
                             last_price=excluded.last_price""",
                        (VENUE, asset, "PERPETUAL", minute, float(bucket["notional"] or 0),
                         float(bucket["buy"] or 0), float(bucket["sell"] or 0), int(bucket["count"] or 0),
                         _safe_float(bucket["price"])),
                    )
            with self._lock:
                self._last_trade_ms = max(self._last_trade_ms, max(rows))
        self._cursors[symbol] = newest

    def _refresh_spot_notional(self, catalog: list[dict[str, Any]]) -> None:
        bases = {str(row.get("base") or "").upper() for row in catalog if row.get("base")}
        with _EXCHANGE_LOCK:
            client = exchange()
            markets = client.load_markets()
            spot_symbols = [symbol for symbol, market in markets.items()
                            if market.get("spot") and market.get("active", True)
                            and str(market.get("base") or "").upper() in bases
                            and str(market.get("quote") or "").upper() in USD_QUOTES]
            tickers = client.fetch_tickers(spot_symbols) if spot_symbols and client.has.get("fetchTickers") else {}
        totals: dict[str, float] = {}
        for symbol in spot_symbols:
            market = markets[symbol]
            asset = str(market.get("base") or "").upper()
            ticker = tickers.get(symbol) or {}
            quote_volume = _safe_float(ticker.get("quoteVolume"))
            if quote_volume is not None and quote_volume >= 0:
                totals[asset] = totals.get(asset, 0.0) + quote_volume
        with self._lock:
            self._spot_24h = totals
            self._spot_updated_ms = int(time.time() * 1000)

    def _sum_flow(self, asset: str, start_ms: int, end_ms: int) -> dict[str, float | int]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(notional_usd),0) notional,
                          COALESCE(SUM(buy_notional_usd),0) buy_notional,
                          COALESCE(SUM(sell_notional_usd),0) sell_notional,
                          COALESCE(SUM(trade_count),0) trade_count,
                          COUNT(DISTINCT minute_ms) minute_count
                   FROM market_flow_minute
                   WHERE canonical_asset=? AND minute_ms>=? AND minute_ms<?""",
                (asset, start_ms, end_ms),
            ).fetchone()
        return {
            "notional": float(row["notional"] or 0),
            "buy_notional": float(row["buy_notional"] or 0),
            "sell_notional": float(row["sell_notional"] or 0),
            "trade_count": int(row["trade_count"] or 0),
            "minute_count": int(row["minute_count"] or 0),
        }

    def _historical_window_samples(self, asset: str, width_ms: int, now_ms: int, days: int = 30) -> list[float]:
        start = now_ms - days * 24 * 60 * 60_000
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT minute_ms, notional_usd FROM market_flow_minute
                   WHERE canonical_asset=? AND minute_ms>=? AND minute_ms<? ORDER BY minute_ms""",
                (asset, start, now_ms),
            ).fetchall()
        if not rows:
            return []
        bins: dict[int, float] = {}
        for row in rows:
            key = int(row["minute_ms"]) // width_ms
            bins[key] = bins.get(key, 0.0) + float(row["notional_usd"] or 0)
        return [value for _, value in sorted(bins.items()) if value > 0]

    @staticmethod
    def _history_change(history: deque[tuple[int, float]], now_ms: int, width_ms: int) -> float | None:
        if not history:
            return None
        current = history[-1][1]
        target = now_ms - width_ms
        previous = None
        for ts, value in reversed(history):
            if ts <= target:
                previous = value
                break
        return _pct_change(current, previous)

    def asset_snapshot(self, market: dict[str, Any], selected_window: str = "8h") -> dict[str, Any]:
        now = int(time.time() * 1000)
        asset = str(market.get("base") or "").upper()
        windows: dict[str, dict[str, Any]] = {}
        for name, width in WINDOW_MS.items():
            observed = self._sum_flow(asset, now - width, now)
            coverage = min(100.0, 100.0 * int(observed["minute_count"]) / max(1, width // 60_000))
            windows[name] = {**observed, "coverage_pct": round(coverage, 1)}
        sessions: dict[str, dict[str, Any]] = {}
        for name in SESSION_SPECS:
            session = session_window(name, now)
            end = min(now, session.end_ms)
            observed = self._sum_flow(asset, session.start_ms, end)
            expected_minutes = max(1, (end - session.start_ms) // 60_000)
            coverage = min(100.0, 100.0 * int(observed["minute_count"]) / expected_minutes)
            sessions[name] = {
                **observed,
                "coverage_pct": round(coverage, 1),
                "start_ms": session.start_ms,
                "end_ms": session.end_ms,
                "active": session.active,
            }
        chosen = sessions.get(selected_window) if selected_window in sessions else windows.get(selected_window, windows["8h"])
        width_ms = WINDOW_MS.get(selected_window, WINDOW_MS["8h"])
        samples = self._historical_window_samples(asset, width_ms, now)
        historical = samples[:-1] if len(samples) > 1 else []
        median = None
        if historical:
            ordered = sorted(historical)
            mid = len(ordered) // 2
            median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
        current_notional = float(chosen.get("notional") or 0)
        relative = current_notional / median if median and median > 0 else None
        percentile = _percentile_rank(historical, current_notional) if historical else None
        reported_derivative_24h = _safe_float(market.get("quote_volume_24h")) or 0.0
        with self._lock:
            spot_24h = float(self._spot_24h.get(asset, 0.0))
            oi_history = self._oi_history.get(asset, deque())
            price_history = self._price_history.get(asset, deque())
        total_24h = spot_24h + reported_derivative_24h
        spot_share = 100.0 * spot_24h / total_24h if total_24h > 0 else None
        derivative_share = 100.0 * reported_derivative_24h / total_24h if total_24h > 0 else None
        buy = float(chosen.get("buy_notional") or 0)
        sell = float(chosen.get("sell_notional") or 0)
        aggressor_total = buy + sell
        imbalance = 100.0 * (buy - sell) / aggressor_total if aggressor_total > 0 else None
        price_change = self._history_change(price_history, now, width_ms)
        oi_change_1h = self._history_change(oi_history, now, WINDOW_MS["1h"])
        oi_change_8h = self._history_change(oi_history, now, WINDOW_MS["8h"])
        state = participation_state(percentile)
        flow_up = relative is not None and relative >= 1.25
        return {
            "asset": asset,
            "selected_window": selected_window,
            "selected_notional_usd": current_notional,
            "selected_coverage_pct": chosen.get("coverage_pct"),
            "notional5m": windows["5m"]["notional"],
            "notional15m": windows["15m"]["notional"],
            "notional1h": windows["1h"]["notional"],
            "notional4h": windows["4h"]["notional"],
            "notional8h": windows["8h"]["notional"],
            "notional24h_observed": windows["24h"]["notional"],
            "notional24h_reported_derivative": reported_derivative_24h,
            "notional24h_reported_spot": spot_24h,
            "notional24h_reported_total": total_24h,
            "spot_share_pct": spot_share,
            "derivative_share_pct": derivative_share,
            "buy_aggressor_notional": buy,
            "sell_aggressor_notional": sell,
            "aggressor_imbalance_pct": imbalance,
            "relative_flow": relative,
            "flow_percentile": percentile,
            "flow_state": state,
            "flow_price_state": flow_price_state(price_change, relative),
            "price_change_selected_pct": price_change,
            "open_interest": _safe_float(market.get("open_interest")),
            "open_interest_change_1h_pct": oi_change_1h,
            "open_interest_change_8h_pct": oi_change_8h,
            "oi_context": oi_context(price_change, flow_up, oi_change_8h),
            "funding_rate": _safe_float(market.get("funding_rate")),
            "sessions": sessions,
            "windows": windows,
            "baseline_samples": len(historical),
            "baseline_median": median,
            "baseline_state": "READY" if len(historical) >= 8 else "WARMING",
            "flow_feed_quality": "PARTIAL_REST" if current_notional > 0 else "WARMING",
            "updated_at_ms": now,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._feed_state,
                "quality": "PARTIAL_REST",
                "last_trade_ms": self._last_trade_ms or None,
                "spot_updated_ms": self._spot_updated_ms or None,
                "runtime_started_ms": self._runtime_started_ms,
                "error": self._feed_error,
                "note": "HTX reported 24h venue notional is complete; shorter windows accumulate from normalized REST trade capture until websocket ingestion is installed.",
            }

    def cleanup(self, retention_days: int = 35) -> None:
        cutoff = int(time.time() * 1000) - retention_days * 24 * 60 * 60_000
        with self._connect() as conn:
            conn.execute("DELETE FROM market_flow_minute WHERE minute_ms < ?", (cutoff,))


market_flow = MarketFlowEngine()
