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
from .models import ScannerRequest
from .presets import STRATEGIES
from .scan_store import scan_store
from .scanner import run_scanner
from .settings import public_settings
from .storage import DB_PATH

logger = logging.getLogger("epinnox.live-intelligence")
ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = ROOT / "config" / "asset_taxonomy.json"


class LiveIntelligenceRuntime:
    """Continuous HTX market observation + bounded evidence qualification.

    Universe and Scanner are independent runtime loops. Pausing a loop prevents
    new work from being admitted; an in-flight atomic scanner batch is allowed
    to finish and persist before the Scanner transitions to PAUSED.
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
        self._events: deque[dict[str, Any]] = deque(maxlen=80)
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
            "evidence_stale_seconds": 14_400
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
                    int(bool(data["universe_enabled"])), int(bool(data["scanner_enabled"])),
                    json.dumps(data["mandate"], separators=(",", ":")), int(time.time() * 1000),
                ),
            )

    def _load_taxonomy(self) -> dict[str, Any]:
        try:
            return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("taxonomy load failed: %s", exc)
            return {"schema_version": 1, "taxonomy_id": "fallback", "categories": {}}

    def _category(self, base: str) -> str:
        for category, assets in self._taxonomy.get("categories", {}).items():
            if base in assets:
                return category
        return "OTHER / UNCLASSIFIED"

    def _recover_evidence(self) -> None:
        for scan in reversed(scan_store.recent_results(60)):
            self._ingest_scan(scan, emit=False)

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
            self._event("runtime_started", "Live Universe and Live Scanner runtime started")

    def shutdown(self) -> None:
        self._stop.set()
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
            self._event("control_changed", f"Universe={'LIVE' if self._state['universe_enabled'] else 'PAUSED'} · Scanner={'LIVE' if self._state['scanner_enabled'] else 'PAUSED'}")
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
        mandate.pop("batch_size", None)
        mandate.pop("market_refresh_seconds", None)
        mandate.pop("scanner_idle_seconds", None)
        mandate.pop("evidence_stale_seconds", None)
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
                self._event("scan_committed", f"Cycle {self._scanner_cycle} · {', '.join(x.split('/')[0] for x in batch)} · {time.time()-started:.1f}s")
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
                if not symbol:
                    continue
                last[symbol] = max(last.get(symbol, 0), int(row.get("__completed_at_ms") or 0))
            ordered = sorted(available, key=lambda symbol: (last.get(symbol, 0) > 0, last.get(symbol, 0), -volume.get(symbol, 0.0), symbol))
            requested = int(self._state["mandate"].get("batch_size", 2))
            count = self._validate_batch_geometry(self._state["mandate"], requested)
        retry_after = 300_000
        eligible = [s for s in ordered if now - last.get(s, 0) >= retry_after or any(k.startswith(s + "|") for k in self._evidence)]
        return (eligible or ordered)[:count]

    def _ingest_scan(self, scan: dict[str, Any], *, emit: bool) -> None:
        completed = int(scan.get("completed_at_ms") or time.time() * 1000)
        scan_id = str(scan.get("scan_id") or "")
        with self._lock:
            for row in scan.get("results", []):
                key = "|".join([
                    str(row.get("symbol") or ""), str(row.get("timeframe") or ""), str(row.get("strategy") or ""),
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

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": 1,
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
                "taxonomy": {"schema_version": self._taxonomy.get("schema_version"), "taxonomy_id": self._taxonomy.get("taxonomy_id")},
                "events": list(self._events)[:30],
            }

    def universe_snapshot(self) -> dict[str, Any]:
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
        volume_rank = sorted((float(x.get("quote_volume_24h") or 0.0), x["symbol"]) for x in catalog)
        rank_lookup = {symbol: idx for idx, (_, symbol) in enumerate(volume_rank)}
        total = max(1, len(volume_rank))
        output: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {}
        for market in catalog:
            symbol = market["symbol"]
            base = str(market.get("base") or symbol.split("/")[0])
            rows = sorted(by_symbol.get(symbol, []), key=self._row_order)
            best = rows[0] if rows else None
            latest = max((int(x.get("__completed_at_ms") or 0) for x in rows), default=0)
            combos = {
                (str(x.get("timeframe")), str(x.get("strategy")), round(float(x.get("target_buffer_pct") or 0), 6))
                for x in rows
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
            qualified = [x for x in rows if x.get("qualified")]
            qualification_state = "QUALIFIED" if qualified else ("REJECTED" if rows else "NO_EVIDENCE")
            category = self._category(base)
            category_counts[category] = category_counts.get(category, 0) + 1
            idx = rank_lookup.get(symbol, 0)
            percentile = idx / total
            liquidity = "HIGH" if percentile >= 0.80 else ("MEDIUM" if percentile >= 0.40 else "THIN")
            move = abs(float(market.get("change_24h_pct") or 0.0))
            volatility = "HIGH" if move >= 8 else ("ELEVATED" if move >= 3 else "NORMAL")
            output.append({
                **market,
                "category": category,
                "liquidity_tier": liquidity,
                "volatility_state": volatility,
                "coverage_state": coverage_state,
                "coverage_pct": round(coverage_pct, 1),
                "qualification_state": qualification_state,
                "latest_evidence_ms": latest or None,
                "evidence_rows": len(rows),
                "qualified_candidates": len(qualified),
                "best": best,
                "strategies": rows[:12],
            })
        return {
            "schema_version": 1,
            "source": "HTX via CCXT",
            "generated_at_ms": now,
            "runtime": status,
            "categories": [{"name": name, "count": count} for name, count in sorted(category_counts.items())],
            "markets": output,
        }


live_intelligence = LiveIntelligenceRuntime()
