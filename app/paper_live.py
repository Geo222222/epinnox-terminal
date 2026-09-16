from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pandas as pd

from .market import fetch_ohlcv
from .models import BacktestRequest
from .storage import RuntimeStore, runtime_store
from .strategies import build_entry_model, entry_receipt


@dataclass
class PaperRuntimeState:
    session_id: str | None = None
    status: str = "STOPPED"
    running: bool = False
    started_at_ms: int | None = None
    last_bar_ts_ms: int | None = None
    last_error: str | None = None
    last_signal: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    layers: int = 0
    bars_in_position: int = 0
    pending_intent: dict[str, Any] | None = None
    recovered_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)


class PaperLiveManager:
    """Durable live-candle strategy runner hard-wired to PAPER upstream state.

    SQLite stores the strategy intent, checkpoints and event journal. epinnox-online
    remains authoritative for paper positions/fills. Browser cookies are deliberately
    never persisted. A restart therefore reconciles upstream state before resuming,
    and fails closed into RECOVERY_REQUIRED if reconciliation cannot be proven.
    """

    def __init__(self, store: RuntimeStore = runtime_store) -> None:
        self.store = store
        self.state = PaperRuntimeState()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._req: BacktestRequest | None = None
        self._base_url: str | None = None
        self._cookie: str = ""
        self._shutdown_for_restart = False

    def snapshot(self) -> dict[str, Any]:
        req = self._req
        events = self.state.events[-50:]
        if self.state.session_id:
            try:
                events = self.store.recent_events(self.state.session_id, 50)
            except Exception:
                pass
        return {
            "session_id": self.state.session_id,
            "status": self.state.status,
            "running": self.state.running,
            "started_at_ms": self.state.started_at_ms,
            "last_bar_ts_ms": self.state.last_bar_ts_ms,
            "last_error": self.state.last_error,
            "last_signal": self.state.last_signal,
            "position": self.state.position,
            "layers": self.state.layers,
            "bars_in_position": self.state.bars_in_position,
            "pending_intent": self.state.pending_intent,
            "recovered_count": self.state.recovered_count,
            "events": events,
            "entry_model": None if req is None else {
                "primary": req.strategy,
                "confirmations": req.confirmations,
                "policy": req.confirmation_policy,
                "required": req.confirmation_required,
                "window_bars": req.confirmation_window_bars,
            },
        }

    def _checkpoint(self, status: str | None = None) -> None:
        if not self.state.session_id or self._req is None:
            return
        if status is not None:
            self.state.status = status
        self.store.save_session(
            self.state.session_id,
            status=self.state.status,
            request=self._req.model_dump(mode="json"),
            started_at_ms=self.state.started_at_ms,
            last_bar_ts_ms=self.state.last_bar_ts_ms,
            last_error=self.state.last_error,
            last_signal=self.state.last_signal,
            position=self.state.position,
            layers=self.state.layers,
            bars_in_position=self.state.bars_in_position,
            pending_intent=self.state.pending_intent,
            recovered_count=self.state.recovered_count,
        )

    def _event(self, kind: str, detail: str, **extra: Any) -> None:
        event = {"ts_ms": int(time.time() * 1000), "kind": kind, "detail": detail, **extra}
        self.state.events.append(event)
        self.state.events = self.state.events[-200:]
        if self.state.session_id:
            self.store.add_event(self.state.session_id, event["ts_ms"], kind, detail, extra or None)
        self._checkpoint()

    async def _json(self, method: str, path: str, *, json: dict | None = None) -> Any:
        if not self._base_url:
            raise RuntimeError("EPINNOX_ONLINE_BASE_URL is not configured")
        headers = {"cookie": self._cookie} if self._cookie else {}
        async with httpx.AsyncClient(base_url=self._base_url.rstrip("/"), timeout=20.0, headers=headers) as client:
            response = await client.request(method, path, json=json)
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail")
                except Exception:
                    detail = response.text
                raise RuntimeError(f"epinnox-online {method} {path} -> {response.status_code}: {detail}")
            return response.json()

    async def _assert_paper(self) -> dict:
        return await self._json("GET", "/api/account/paper-state")

    async def _positions(self) -> list[dict]:
        rows = await self._json("GET", "/api/positions")
        return rows if isinstance(rows, list) else []

    def _find_position(self, rows: list[dict], symbol: str) -> dict | None:
        target = symbol.split(":", 1)[0].upper()
        for row in rows:
            rs = str(row.get("symbol") or "").split(":", 1)[0].upper()
            if rs == target:
                return row
        return None

    def _target(self, avg: float, side: str, req: BacktestRequest) -> tuple[float, float]:
        entry_r = req.entry_fee_pct / 100.0
        exit_r = req.exit_fee_pct / 100.0
        extra_r = req.extra_cost_pct / 100.0
        profit_r = req.desired_net_profit_pct / 100.0
        if side == "long":
            be = avg * (1 + entry_r + extra_r) / max(1e-12, 1 - exit_r)
            target = avg * (1 + entry_r + extra_r + profit_r) / max(1e-12, 1 - exit_r)
        else:
            be = avg * (1 - entry_r - extra_r) / (1 + exit_r)
            target = avg * (1 - entry_r - extra_r - profit_r) / (1 + exit_r)
        return be, target

    async def _arm_exits(self, pos: dict, req: BacktestRequest) -> None:
        side = str(pos.get("side") or "")
        avg = float(pos.get("entry_price") or 0.0)
        if avg <= 0 or side not in {"long", "short"}:
            return
        be, target = self._target(avg, side, req)
        stop = None
        if req.stop_loss_pct:
            x = req.stop_loss_pct / 100.0
            stop = avg * (1 - x) if side == "long" else avg * (1 + x)
        await self._assert_paper()
        await self._json("PATCH", "/api/positions/sl-tp", json={
            "symbol": str(pos.get("symbol") or req.symbol),
            "side": side,
            "stop_loss": stop,
            "take_profit": target,
        })
        self._event("exit_armed", f"{side} break-even {be:.8g}, target {target:.8g}", break_even=be, target=target, stop=stop)

    async def _submit_entry(self, side: str, signal_price: float, receipt: list[dict], req: BacktestRequest, bar_ts: int) -> None:
        paper = await self._assert_paper()
        equity = float(paper.get("equity_usdt") or paper.get("cash_usdt") or 0.0)
        if equity <= 0:
            raise RuntimeError("Paper account equity is unavailable or non-positive")
        notional = equity * req.leverage * (req.allocation_pct / 100.0)
        qty = notional / signal_price if signal_price > 0 else 0.0
        if qty <= 0:
            raise RuntimeError("Calculated paper order quantity is zero")
        next_layer = self.state.layers + 1
        client_order_id = f"terminal-{(self.state.session_id or 'session')[:8]}-{bar_ts}-{side}-{next_layer}"
        payload = {
            "symbol": req.symbol,
            "side": "buy" if side == "long" else "sell",
            "type": "market",
            "qty": qty,
            "qty_mode": "units",
            "leverage": req.leverage,
            "margin_mode": "cross",
            "client_order_id": client_order_id,
        }
        self.state.pending_intent = {
            "bar_ts_ms": bar_ts,
            "side": side,
            "layer": next_layer,
            "qty": qty,
            "client_order_id": client_order_id,
        }
        self._event("intent_pending", f"{side} layer {next_layer} {client_order_id}", receipt=receipt)
        await self._assert_paper()
        order = await self._json("POST", "/api/orders", json=payload)
        self.state.layers = next_layer
        self.state.bars_in_position = 0 if self.state.layers == 1 else self.state.bars_in_position
        self._event("entry_submitted", f"{side} layer {self.state.layers} qty={qty:.8g}", order=order, receipt=receipt, client_order_id=client_order_id)
        for _ in range(8):
            rows = await self._positions()
            pos = self._find_position(rows, req.symbol)
            if pos:
                self.state.position = pos
                self.state.pending_intent = None
                self._checkpoint()
                await self._arm_exits(pos, req)
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("Paper order returned but position did not appear; pending intent retained for restart reconciliation")

    async def _close_for_timeout(self, pos: dict, req: BacktestRequest) -> None:
        await self._assert_paper()
        await self._json("POST", "/api/positions/close", json={
            "symbol": str(pos.get("symbol") or req.symbol),
            "side": str(pos.get("side")),
            "qty": None,
        })
        self._event("timeout_close", f"closed after {self.state.bars_in_position} completed bars")
        self.state.position = None
        self.state.layers = 0
        self.state.bars_in_position = 0
        self.state.pending_intent = None
        self._checkpoint()

    async def start(self, req: BacktestRequest, base_url: str | None, cookie: str) -> dict[str, Any]:
        if self._task and not self._task.done():
            raise RuntimeError("A paper live session is already running")
        if not base_url:
            raise RuntimeError("Set EPINNOX_ONLINE_BASE_URL before starting PAPER")
        self._req = req
        self._base_url = base_url
        self._cookie = cookie
        self._stop = asyncio.Event()
        self._shutdown_for_restart = False
        self.state = PaperRuntimeState(
            session_id=str(uuid.uuid4()),
            status="RUNNING",
            running=True,
            started_at_ms=int(time.time() * 1000),
        )
        await self._assert_paper()
        self._checkpoint()
        self._event("started", f"{req.symbol} {req.timeframe} {req.confirmation_policy}")
        self._task = asyncio.create_task(self._loop())
        return self.snapshot()

    async def recover(self, base_url: str | None, cookie: str = "") -> dict[str, Any]:
        active = self.store.load_active_session()
        if not active:
            return self.snapshot()
        if self._task and not self._task.done():
            return self.snapshot()
        self._req = BacktestRequest.model_validate(active["request"])
        self._base_url = base_url
        self._cookie = cookie
        self._stop = asyncio.Event()
        self._shutdown_for_restart = False
        self.state = PaperRuntimeState(
            session_id=active["session_id"],
            status="RECONCILING",
            running=False,
            started_at_ms=active["started_at_ms"],
            last_bar_ts_ms=active["last_bar_ts_ms"],
            last_error=active["last_error"],
            last_signal=active["last_signal"],
            position=active["position"],
            layers=int(active["layers"] or 0),
            bars_in_position=int(active["bars_in_position"] or 0),
            pending_intent=active["pending_intent"],
            recovered_count=int(active["recovered_count"] or 0),
        )
        self._checkpoint("RECONCILING")
        if not base_url:
            self.state.last_error = "EPINNOX_ONLINE_BASE_URL is not configured; persisted paper session requires recovery"
            self._checkpoint("RECOVERY_REQUIRED")
            return self.snapshot()
        try:
            await self._assert_paper()
            rows = await self._positions()
            pos = self._find_position(rows, self._req.symbol)
            self.state.position = pos
            if pos is None:
                if self.state.pending_intent:
                    raise RuntimeError("A pre-restart order intent is unresolved and no upstream position exists; refusing duplicate submission")
                self.state.layers = 0
                self.state.bars_in_position = 0
            else:
                if self.state.layers <= 0:
                    self.state.layers = 1
                if self.state.pending_intent:
                    self._event("intent_reconciled", "pending pre-restart intent reconciled to authoritative upstream position", intent=self.state.pending_intent)
                    self.state.pending_intent = None
                await self._arm_exits(pos, self._req)
            self.state.recovered_count += 1
            self.state.last_error = None
            self.state.running = True
            self._checkpoint("RECOVERED")
            self._event("recovered_after_restart", f"session recovered; upstream position={'present' if pos else 'flat'}")
            self._task = asyncio.create_task(self._loop())
        except Exception as exc:
            self.state.running = False
            self.state.last_error = str(exc)
            self._checkpoint("RECOVERY_REQUIRED")
            self._event("recovery_required", str(exc))
        return self.snapshot()

    async def stop(self) -> dict[str, Any]:
        self._stop.set()
        task = self._task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.state.running = False
        self.state.pending_intent = None
        self._event("stopped", "paper live runner stopped; existing paper positions were left untouched")
        self._checkpoint("STOPPED")
        return self.snapshot()

    async def shutdown(self) -> None:
        """Checkpoint an active runner without converting user intent to STOPPED."""
        task = self._task
        if not task or task.done():
            return
        self._shutdown_for_restart = True
        self._stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self.state.running = False
        self._event("server_shutdown_checkpoint", "server shutdown checkpoint saved; session remains recoverable")
        self._checkpoint("RUNNING")

    async def _loop(self) -> None:
        assert self._req is not None
        req = self._req
        try:
            while not self._stop.is_set():
                try:
                    candles = await asyncio.to_thread(fetch_ohlcv, req.symbol, req.timeframe, max(250, min(req.limit, 1000)))
                    if len(candles) < 50:
                        raise RuntimeError("Not enough market history for live signal evaluation")
                    df = pd.DataFrame(candles)
                    i = len(df) - 2
                    bar_ts = int(df.ts_ms.iloc[i])
                    if self.state.last_bar_ts_ms == bar_ts:
                        await asyncio.sleep(2.0)
                        continue
                    self.state.last_bar_ts_ms = bar_ts
                    self.state.last_error = None
                    self._checkpoint()
                    logic = build_entry_model(
                        df,
                        req.strategy,
                        req.timeframe,
                        req.manual_params,
                        req.confirmations,
                        req.confirmation_policy,
                        req.confirmation_required,
                        req.confirmation_window_bars,
                    )
                    rows = await self._positions()
                    pos = self._find_position(rows, req.symbol)
                    if pos is None:
                        self.state.position = None
                        self.state.layers = 0
                        self.state.bars_in_position = 0
                    else:
                        self.state.position = pos
                        self.state.bars_in_position += 1
                        if req.max_bars_in_trade and self.state.bars_in_position >= req.max_bars_in_trade:
                            await self._close_for_timeout(pos, req)
                            await asyncio.sleep(1.0)
                            continue
                    self._checkpoint()

                    allow_long = req.direction in {"Both", "Long Only"}
                    allow_short = req.direction in {"Both", "Short Only"}
                    sig_side = None
                    if allow_long and bool(logic["long"].iloc[i]):
                        sig_side = "long"
                    elif allow_short and bool(logic["short"].iloc[i]):
                        sig_side = "short"
                    if sig_side:
                        receipt = entry_receipt(logic, i, sig_side)
                        self.state.last_signal = {"ts_ms": bar_ts, "side": sig_side, "receipt": receipt}
                        self._checkpoint()
                        same_side = pos is not None and str(pos.get("side")) == sig_side
                        can_enter = pos is None or (same_side and self.state.layers < req.pyramiding)
                        if can_enter:
                            await self._submit_entry(sig_side, float(df.close.iloc[i]), receipt, req, bar_ts)
                        else:
                            self._event("signal_skipped", f"{sig_side} signal blocked by current position/pyramiding", receipt=receipt)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.state.last_error = str(exc)
                    self._event("error", str(exc))
                await asyncio.sleep(2.0)
        finally:
            self.state.running = False
            if self._shutdown_for_restart:
                self._checkpoint("RUNNING")
            elif self._stop.is_set():
                self._checkpoint("STOPPED")
            else:
                self._checkpoint("RECOVERY_REQUIRED")
