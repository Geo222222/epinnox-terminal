from __future__ import annotations

from collections import deque
from copy import deepcopy
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from .market import market_catalog, symbols
from .market_flow import market_flow
from .models import ScannerRequest
from .presets import STRATEGIES
from .scan_store import scan_store
from .scanner import run_scanner
from .settings import public_settings
from .storage import DB_PATH

logger = logging.getLogger("epinnox.live-intelligence")
ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = ROOT / "config" / "asset_taxonomy.json"
FLOW_WINDOWS = {"5m", "1h", "4h", "8h", "24h", "NEW_YORK", "LONDON", "ASIA"}


class LiveIntelligenceRuntime:
    """One continuous runtime for Universe market state and Scanner evidence.

    The Universe owns canonical market observation and market-flow state. The
    Scanner consumes the same symbol catalog and persists deterministic evidence.
    Pausing either surface suppresses its own updates without creating a second
    data path or destroying the other runtime.
    """

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._market_thread: threading.Thread | None = None
        self._scanner_thread: threading.Thread | None = None
        self._started = False
        self._catalog: list[dict[str, Any]] = []
        self._evidence: dict[str, dict[str, Any]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=120)
        self._market_state = "STARTING"
        self._scanner_state = "STARTING"
        self._market_error: str | None = None
        self._scanner_error: str | None = None
        self._market_generation = 0
        self._scanner_cycle = 0
        self._last_market_tick_ms = 0
        self._last_evidence_commit_ms = 0
        self._active_batch: list[str] = []
        self._taxonomy = self._load_taxonomy()
        self._state = self._load_state()
        self._recover_evidence()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_state_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_intelligence_state (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    universe_enabled INTEGER NOT NULL,
                    scanner_enabled INTEGER NOT NULL,
                    mandate_json TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                """
            )

    def _default_mandate(self) -> dict[str, Any]:
        defaults = public_settings().get("scanner_defaults", {})
        strategies = [x for x in defaults.get("strategies", []) if x in STRATEGIES] or [
            "Supertrend", "Stochastic Reversal", "EMA Crossover", "Bollinger Mean Reversion"
        ]
        timeframes = [x for x in defaults.get("timeframes", []) if x in {"1m", "5m", "15m", "30m"}] or ["1m", "5m"]
        return {
            "objective": defaults.get("objective", "Capital Growth"),
            "timeframes": timeframes,
            "strategies": strategies,
            "history_bars": int(defaults.get("history_bars", 2000)),
            "target_buffers_pct": list(defaults.get("target_buffers_pct", [0.0, 0.005, 0.01, 0.02, 0.04, 0.08])),
            "walk_forward_windows": int(defaults.get("walk_forward_windows", 4)),
            "min_sample_trades": int(defaults.get("min_sample_trades", 20)),
            "min_walk_forward_pass_rate_pct": float(defaults.get("min_walk_forward_pass_rate_pct", 60.0)),
            "max_drawdown_pct": float(defaults.get("max_drawdown_pct", 5.0)),
            "min_net_expectancy_usdt": float(defaults.get("min_net_expectancy_usdt", 0.0)),
            "holdout_fraction": float(defaults.get("holdout_fraction", 0.25)),
            "min_holdout_trades": int(defaults.get("min_holdout_trades", 5)),
            "min_holdout_expectancy_usdt": float(defaults.get("min_holdout_expectancy_usdt", 0.0)),
            "starting_balance": float(defaults.get("starting_balance", 100000.0)),
            "leverage": float(defaults.get("leverage", 1.0)),
            "allocation_pct": float(defaults.get("allocation_pct", 5.0)),
            "pyramiding": 1,
            "direction": "Both",
            "entry_fee_pct": float(defaults.get("entry_fee_pct", 0.05)),
            "exit_fee_pct": float(defaults.get("exit_fee_pct", 0.05)),
            "extra_cost_pct": float(defaults.get("extra_cost_pct", 0.0)),
            "referral_share_pct": float(defaults.get("referral_share_pct", 30.0)),
            "maintenance_margin_pct": float(defaults.get("maintenance_margin_pct", 0.4)),
            "backtest_profile": "TradingView Parity",
            "batch_size": 2,
            "market_refresh_seconds": 5,
            "scanner_idle_seconds": 2,
            "evidence_stale_seconds": 14_400,
        }

    def _load_state(self) -> dict[str, Any]:
        self._init_state_schema()
        default = {"universe_enabled": True, "scanner_enabled": True, "mandate": self._default_mandate()}
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM live_intelligence_state WHERE id=1").fetchone()
        if row is None:
            self._persist_state(default)
            return default
        try:
            mandate = {**default["mandate"], **json.loads(row["mandate_json"])}
        except (TypeError, json.JSONDecodeError):
            mandate = default["mandate"]
        return {
            "universe_enabled": bool(row["universe_enabled"]),
            "scanner_enabled": bool(row["scanner_enabled"]),
            "mandate": mandate,
        }

    def _persist_state(self, state: dict[str, Any] | None = None) -> None:
        data = state or self._state
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO live_intelligence_state(id,universe_enabled,scanner_enabled,mandate_json,updated_at_ms)
                   VALUES(1,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     universe_enabled=excluded.universe_enabled,
                     scanner_enabled=excluded.scanner_enabled,
                     mandate_json=excluded.mandate_json,
                     updated_at_ms=excluded.updated_at_ms""",
                (
                    int(bool(data["universe_enabled"])),
                    int(bool(data["scanner_enabled"])),
                    json.dumps(data["mandate"], separators=(",", ":")),
                    int(time.time() * 1000),
                ),
            )

    def _load_taxonomy(self) -> dict[str, Any]:
        try:
            return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("taxonomy load failed: %s", exc)
            return {"schema_version": 1, "taxonomy_id": "fallback", "categories": {}}

    def _category(self, base: str) -> str:
        aliases = {
            "MAJORS": "MAJOR",
            "LARGE_CAP": "LARGE_CAP",
            "ALTCOINS": "ALTCOIN",
            "MEME": "MEME",
            "DEFI": "DEFI",
            "AI": "AI",
            "L1": "L1",
            "L2": "L2",
            "RWA": "RWA",
            "STABLECOINS": "STABLECOIN",
        }
        for category, assets in self._taxonomy.get("categories", {}).items():
            if base in assets:
                return aliases.get(str(category).upper(), str(category).upper().replace(" / ", "_"))
        return "OTHER"

    def _recover_evidence(self) -> None:
        for scan in reversed(scan_store.recent_results(60)):
            self._ingest_scan(scan, emit=False)

    def _catalog_copy(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._catalog)

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            self._market_thread = threading.Thread(target=self._market_loop, name="epinnox-live-universe", daemon=True)
            self._scanner_thread = threading.Thread(target=self._scanner_loop, name="epinnox-live-scanner", daemon=True)
            self._market_thread.start()
            self._scanner_thread.start()
            market_flow.start(self._catalog_copy)
            self._event("runtime_started", "Live Universe, flow collector, and Live Scanner started")

    def shutdown(self) -> None:
        self._stop.set()
        market_flow.shutdown()
        for thread in (self._market_thread, self._scanner_thread):
            if thread and thread.is_alive():
                thread.join(timeout=1.5)
        with self._lock:
            self._started = False

    def set_controls(self, *, universe_enabled: bool | None = None, scanner_enabled: bool | None = None) -> dict[str, Any]:
        with self._lock:
            if universe_enabled is not None:
                self._state["universe_enabled"] = bool(universe_enabled)
                self._market_state = "STARTING" if universe_enabled else "PAUSED"
            if scanner_enabled is not None:
                self._state["scanner_enabled"] = bool(scanner_enabled)
                if not scanner_enabled and self._active_batch:
                    self._scanner_state = "PAUSING"
                else:
                    self._scanner_state = "STARTING" if scanner_enabled else "PAUSED"
            self._persist_state()
            self._event(
                "control_changed",
                f"Universe={'LIVE' if self._state['universe_enabled'] else 'PAUSED'} · "
                f"Scanner={'LIVE' if self._state['scanner_enabled'] else 'PAUSED'}",
            )
        return self.status()

    def update_mandate(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = set(self._default_mandate())
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unsupported mandate fields: {', '.join(sorted(unknown))}")
        merged = {**self._state["mandate"], **payload}
        merged["strategies"] = list(dict.fromkeys(x for x in merged.get("strategies", []) if x in STRATEGIES))
        merged["timeframes"] = list(dict.fromkeys(x for x in merged.get("timeframes", []) if x in {"1m", "5m", "15m", "30m"}))
        merged["target_buffers_pct"] = sorted(set(float(x) for x in merged.get("target_buffers_pct", []) if float(x) >= 0))
        merged["batch_size"] = max(1, min(6, int(merged.get("batch_size", 2))))
        if not merged["strategies"] or not merged["timeframes"] or not merged["target_buffers_pct"]:
            raise ValueError("Live Scanner mandate requires at least one strategy, timeframe, and target")
        self._validate_batch_geometry(merged, 1)
        with self._lock:
            self._state["mandate"] = merged
            self._persist_state()
            self._event("mandate_updated", "Live Scanner mandate updated")
        return self.status()

    def _validate_batch_geometry(self, mandate: dict[str, Any], requested: int) -> int:
        per_symbol = len(mandate["timeframes"]) * len(mandate["strategies"]) * len(mandate["target_buffers_pct"])
        windows = int(mandate["walk_forward_windows"])
        max_by_eval = max(1, 1200 // max(1, per_symbol))
        max_by_sim = max(1, 6000 // max(1, per_symbol * (2 + windows)))
        return max(1, min(requested, max_by_eval, max_by_sim))

    def _scanner_request(self, selected_symbols: list[str]) -> ScannerRequest:
        mandate = deepcopy(self._state["mandate"])
        for key in ("batch_size", "market_refresh_seconds", "scanner_idle_seconds", "evidence_stale_seconds"):
            mandate.pop(key, None)
        return ScannerRequest(symbols=selected_symbols, **mandate)

    def _market_loop(self) -> None:
        while not self._stop.is_set():
            if not self._state["universe_enabled"]:
                with self._lock:
                    self._market_state = "PAUSED"
                self._stop.wait(0.5)
                continue
            try:
                with self._lock:
                    self._market_state = "RUNNING"
                rows = market_catalog()
                now = int(time.time() * 1000)
                market_flow.observe_catalog(rows)
                with self._lock:
                    self._catalog = rows
                    self._market_generation += 1
                    self._last_market_tick_ms = now
                    self._market_error = None
                    self._market_state = "RUNNING"
            except Exception as exc:
                logger.exception("live market refresh failed")
                with self._lock:
                    self._market_error = str(exc)
                    self._market_state = "DEGRADED"
                self._event("market_error", str(exc))
            interval = max(2, min(60, int(self._state["mandate"].get("market_refresh_seconds", 5))))
            self._stop.wait(interval)

    def _scanner_loop(self) -> None:
        while not self._stop.is_set():
            if not self._state["scanner_enabled"]:
                with self._lock:
                    self._scanner_state = "PAUSED"
                    self._active_batch = []
                self._stop.wait(0.5)
                continue
            try:
                available = [row["symbol"] for row in self._catalog] or symbols()
                batch = self._next_batch(available)
                if not batch:
                    with self._lock:
                        self._scanner_state = "IDLE"
                    self._stop.wait(1.0)
                    continue
                with self._lock:
                    self._scanner_state = "RUNNING"
                    self._active_batch = batch
                    self._scanner_error = None
                req = self._scanner_request(batch)
                started = time.time()
                result = run_scanner(req)
                scan_store.save(result)
                self._ingest_scan(result, emit=True)
                with self._lock:
                    self._scanner_cycle += 1
                    self._last_evidence_commit_ms = int(time.time() * 1000)
                    self._active_batch = []
                    self._scanner_state = "RUNNING" if self._state["scanner_enabled"] else "PAUSED"
                self._event(
                    "scan_committed",
                    f"Cycle {self._scanner_cycle} · {', '.join(x.split('/')[0] for x in batch)} · {time.time()-started:.1f}s",
                )
            except Exception as exc:
                logger.exception("live scanner batch failed")
                with self._lock:
                    failed = list(self._active_batch)
                    now = int(time.time() * 1000)
                    for symbol in failed:
                        marker = self._evidence.setdefault(f"__error__|{symbol}", {"symbol": symbol})
                        marker["__completed_at_ms"] = now
                        marker["__error"] = str(exc)
                    self._active_batch = []
                    self._scanner_error = str(exc)
                    self._scanner_state = "DEGRADED"
                self._event("scanner_error", str(exc))
            idle = max(0.5, min(30.0, float(self._state["mandate"].get("scanner_idle_seconds", 2))))
            self._stop.wait(idle)

    def _next_batch(self, available: list[str]) -> list[str]:
        now = int(time.time() * 1000)
        last: dict[str, int] = {}
        with self._lock:
            volume = {row["symbol"]: float(row.get("quote_volume_24h") or 0.0) for row in self._catalog}
            for row in self._evidence.values():
                symbol = str(row.get("symbol") or "")
                if symbol:
                    last[symbol] = max(last.get(symbol, 0), int(row.get("__completed_at_ms") or 0))
            ordered = sorted(
                available,
                key=lambda symbol: (last.get(symbol, 0) > 0, last.get(symbol, 0), -volume.get(symbol, 0.0), symbol),
            )
            requested = int(self._state["mandate"].get("batch_size", 2))
            count = self._validate_batch_geometry(self._state["mandate"], requested)
        retry_after = 300_000
        eligible = [
            symbol for symbol in ordered
            if now - last.get(symbol, 0) >= retry_after or any(key.startswith(symbol + "|") for key in self._evidence)
        ]
        return (eligible or ordered)[:count]

    def _ingest_scan(self, scan: dict[str, Any], *, emit: bool) -> None:
        completed = int(scan.get("completed_at_ms") or time.time() * 1000)
        scan_id = str(scan.get("scan_id") or "")
        with self._lock:
            for row in scan.get("results", []):
                key = "|".join([
                    str(row.get("symbol") or ""),
                    str(row.get("timeframe") or ""),
                    str(row.get("strategy") or ""),
                    f"{float(row.get('target_buffer_pct') or 0):.8f}",
                ])
                existing = self._evidence.get(key)
                if existing and int(existing.get("__completed_at_ms") or 0) > completed:
                    continue
                self._evidence[key] = {**row, "__completed_at_ms": completed, "__scan_id": scan_id}
        if emit:
            self._last_evidence_commit_ms = max(self._last_evidence_commit_ms, completed)

    def _event(self, kind: str, message: str) -> None:
        with self._lock:
            self._events.appendleft({"ts_ms": int(time.time() * 1000), "kind": kind, "message": message})

    @staticmethod
    def _row_order(row: dict[str, Any]) -> tuple[int, int, float]:
        return (
            0 if row.get("qualified") else 1,
            int(row.get("objective_rank") or 1_000_000_000),
            -float(row.get("robustness_score") or 0.0),
        )

    @staticmethod
    def _scanner_components(best: dict[str, Any] | None, coverage_pct: float) -> dict[str, float]:
        if not best:
            return {"evidence": 0.0, "robustness": 0.0, "qualification": 0.0, "coverage": round(coverage_pct, 2)}
        robustness = max(0.0, min(100.0, float(best.get("robustness_score") or 0.0)))
        qualification = 100.0 if best.get("qualified") else 0.0
        expectancy = float(best.get("net_expectancy_usdt") or 0.0)
        evidence = max(0.0, min(100.0, 50.0 + expectancy * 5.0))
        return {
            "evidence": round(evidence, 2),
            "robustness": round(robustness, 2),
            "qualification": qualification,
            "coverage": round(coverage_pct, 2),
        }

    @staticmethod
    def _scanner_score(components: dict[str, float]) -> float:
        return round(
            0.25 * components["evidence"]
            + 0.35 * components["robustness"]
            + 0.25 * components["qualification"]
            + 0.15 * components["coverage"],
            2,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": 2,
                "started": self._started,
                "controls": {
                    "universe_enabled": bool(self._state["universe_enabled"]),
                    "scanner_enabled": bool(self._state["scanner_enabled"]),
                },
                "universe": {
                    "state": self._market_state,
                    "generation": self._market_generation,
                    "markets": len(self._catalog),
                    "last_tick_ms": self._last_market_tick_ms or None,
                    "error": self._market_error,
                    "flow": market_flow.status(),
                },
                "scanner": {
                    "state": self._scanner_state,
                    "cycle": self._scanner_cycle,
                    "active_batch": list(self._active_batch),
                    "last_commit_ms": self._last_evidence_commit_ms or None,
                    "evidence_rows": sum(1 for key in self._evidence if not key.startswith("__error__|")),
                    "error": self._scanner_error,
                },
                "mandate": deepcopy(self._state["mandate"]),
                "taxonomy": {
                    "schema_version": self._taxonomy.get("schema_version"),
                    "taxonomy_id": self._taxonomy.get("taxonomy_id"),
                },
                "events": list(self._events)[:30],
            }

    def universe_snapshot(self, selected_window: str = "8h") -> dict[str, Any]:
        selected_window = "5m" if selected_window == "LIVE" else selected_window
        if selected_window not in FLOW_WINDOWS:
            raise ValueError(f"Unsupported Universe flow window: {selected_window}")
        with self._lock:
            catalog = deepcopy(self._catalog)
            evidence = [deepcopy(row) for key, row in self._evidence.items() if not key.startswith("__error__|")]
            status = self.status()
            mandate = deepcopy(self._state["mandate"])
        by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in evidence:
            by_symbol.setdefault(str(row.get("symbol") or ""), []).append(row)
        expected = max(1, len(mandate["strategies"]) * len(mandate["timeframes"]) * len(mandate["target_buffers_pct"]))
        now = int(time.time() * 1000)
        stale_ms = int(float(mandate.get("evidence_stale_seconds", 14_400)) * 1000)
        assets: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {}
        for market in catalog:
            symbol = str(market["symbol"])
            base = str(market.get("base") or symbol.split("/")[0]).upper()
            rows = sorted(by_symbol.get(symbol, []), key=self._row_order)
            best = rows[0] if rows else None
            latest = max((int(row.get("__completed_at_ms") or 0) for row in rows), default=0)
            combos = {
                (str(row.get("timeframe")), str(row.get("strategy")), round(float(row.get("target_buffer_pct") or 0), 6))
                for row in rows
            }
            coverage_pct = min(100.0, 100.0 * len(combos) / expected)
            if not rows:
                coverage_state = "UNSCANNED"
            elif latest and now - latest > stale_ms:
                coverage_state = "STALE"
            elif coverage_pct < 99.5:
                coverage_state = "PARTIAL"
            else:
                coverage_state = "COVERED"
            qualified = [row for row in rows if row.get("qualified")]
            qualification_state = "QUALIFIED" if qualified else ("REJECTED" if rows else "NO_EVIDENCE")
            category = self._category(base)
            category_counts[category] = category_counts.get(category, 0) + 1
            move = abs(float(market.get("change_24h_pct") or 0.0))
            volatility = "HIGH" if move >= 8 else ("ELEVATED" if move >= 3 else "NORMAL")
            flow = market_flow.asset_snapshot(market, selected_window)
            components = self._scanner_components(best, coverage_pct)
            scanner_score = self._scanner_score(components)
            assets.append({
                "id": f"HTX:{base}:PERPETUAL",
                "canonical_symbol": base,
                "base_asset": base,
                "quote_asset": "USDT",
                "category": category,
                "active": bool(market.get("active", True)),
                "enabled": True,
                "instruments": [{
                    "id": f"HTX:{symbol}",
                    "canonical_symbol": base,
                    "base_asset": base,
                    "quote_asset": "USDT",
                    "venue": "HTX",
                    "venue_symbol": symbol,
                    "instrument_type": "PERPETUAL",
                    "active": bool(market.get("active", True)),
                    "enabled": True,
                }],
                "symbol": symbol,
                "venue": "HTX",
                "instrument_type": "PERPETUAL",
                "price": market.get("price"),
                "change_24h_pct": market.get("change_24h_pct"),
                "bid": market.get("bid"),
                "ask": market.get("ask"),
                "high_24h": market.get("high_24h"),
                "low_24h": market.get("low_24h"),
                "ticker_ts_ms": market.get("ticker_ts_ms"),
                "volatility_state": volatility,
                "freshness_state": "LIVE" if now - int(market.get("ticker_ts_ms") or now) <= 15_000 else "STALE",
                "flow": flow,
                "coverage_state": coverage_state,
                "coverage_pct": round(coverage_pct, 1),
                "qualification_state": qualification_state,
                "latest_evidence_ms": latest or None,
                "evidence_rows": len(rows),
                "qualified_candidates": len(qualified),
                "scanner_score": scanner_score,
                "scanner_score_components": components,
                "best": best,
                "strategies": rows[:12],
            })
        assets.sort(
            key=lambda row: (
                -(float(row["flow"].get("flow_percentile") or -1.0)),
                -(float(row["flow"].get("notional24h_reported_total") or 0.0)),
                row["canonical_symbol"],
            )
        )
        total_reported = sum(float(row["flow"].get("notional24h_reported_total") or 0.0) for row in assets)
        total_spot = sum(float(row["flow"].get("notional24h_reported_spot") or 0.0) for row in assets)
        total_derivatives = sum(float(row["flow"].get("notional24h_reported_derivative") or 0.0) for row in assets)
        high = sum(1 for row in assets if row["flow"].get("flow_state") == "HIGH_PARTICIPATION")
        extreme = sum(1 for row in assets if row["flow"].get("flow_state") == "EXTREME")
        return {
            "schema_version": 2,
            "source": "HTX canonical market + normalized flow collector",
            "generated_at_ms": now,
            "selected_window": selected_window,
            "runtime": status,
            "summary": {
                "assets": len(assets),
                "active": sum(1 for row in assets if row["active"]),
                "high_participation": high,
                "extreme": extreme,
                "reported_notional_24h_total": total_reported,
                "reported_notional_24h_spot": total_spot,
                "reported_notional_24h_derivatives": total_derivatives,
                "flow_quality": market_flow.status().get("quality"),
            },
            "categories": [{"name": name, "count": count} for name, count in sorted(category_counts.items())],
            "assets": assets,
            "markets": assets,
        }


live_intelligence = LiveIntelligenceRuntime()
