from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pandas as pd

from .economics import fee_aware_exit_levels
from .market import fetch_ohlcv
from .models import BacktestRequest
from .storage import RuntimeStore, runtime_store
from .strategies import build_entry_model, entry_receipt


@dataclass
class PaperRuntimeState:
    session_id: str | None = None
    name: str | None = None
    account_id: str | None = None
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
    """One durable paper strategy runner bound to one Epinnox Online account."""

    def __init__(self, store: RuntimeStore = runtime_store) -> None:
        self.store = store
        self.state = PaperRuntimeState()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._req: BacktestRequest | None = None
        self._base_url: str | None = None
        self._cookie: str = ""
        self._shutdown_for_restart = False

    @property
    def request(self) -> BacktestRequest | None:
        return self._req

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
            "name": self.state.name,
            "environment": "PAPER",
            "account_id": self.state.account_id,
            "symbol": None if req is None else req.symbol,
            "timeframe": None if req is None else req.timeframe,
            "strategy": None if req is None else req.strategy,
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
        request = self._req.model_dump(mode="json")
        request["_terminal_account_id"] = self.state.account_id
        request["_terminal_session_name"] = self.state.name
        self.store.save_session(
            self.state.session_id,
            status=self.state.status,
            request=request,
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
                    body = response.json()
                    detail = body.get("detail", body) if isinstance(body, dict) else body
                except Exception:
                    detail = response.text
                raise RuntimeError(f"epinnox-online {method} {path} -> {response.status_code}: {detail}")
            return response.json() if response.content else None

    async def _assert_paper(self) -> dict:
        if not self.state.account_id:
            raise RuntimeError("paper runner has no bound account id")
        accounts = await self._json("GET", "/api/exchange-accounts")
        match = next((row for row in accounts if str(row.get("id") or "") == self.state.account_id), None) if isinstance(accounts, list) else None
        if not match:
            raise RuntimeError("bound paper account is no longer available to this user")
        if str(match.get("account_mode") or "").lower() != "paper":
            raise RuntimeError("bound account is no longer a paper account")
        if not bool(match.get("is_active")):
            raise RuntimeError("paper account context changed; runner stopped before mutation")
        state = await self._json("GET", "/api/account/paper-state")
        if not isinstance(state, dict):
            raise RuntimeError("paper state response was invalid")
        return state

    async def _positions(self) -> list[dict]:
        rows = await self._json("GET", "/api/positions")
        return rows if isinstance(rows, list) else []

    @staticmethod
    def _find_position(rows: list[dict], symbol: str) -> dict | None:
        target = symbol.split(":", 1)[0].upper()
        for row in rows:
            if str(row.get("symbol") or "").split(":", 1)[0].upper() == target:
                return row
        return None

    @staticmethod
    def _target(avg: float, side: str, req: BacktestRequest) -> tuple[float, float]:
        levels = fee_aware_exit_levels(
            avg,
            side,
            entry_fee_pct=req.entry_fee_pct,
            exit_fee_pct=req.exit_fee_pct,
            extra_cost_pct=req.extra_cost_pct,
            desired_net_profit_pct=req.desired_net_profit_pct,
        )
        return levels.break_even, levels.target

    async def _arm_exits(self, pos: dict, req: BacktestRequest) -> None:
        side, avg = str(pos.get("side") or ""), float(pos.get("entry_price") or 0.0)
        if avg <= 0 or side not in {"long", "short"}:
            return
        be, target = self._target(avg, side, req)
        stop = None
        if req.stop_loss_pct:
            x = req.stop_loss_pct / 100.0
            stop = avg * (1 - x) if side == "long" else avg * (1 + x)
        await self._assert_paper()
        await self._json("PATCH", "/api/positions/sl-tp", json={
            "symbol": str(pos.get("symbol") or req.symbol), "side": side,
            "stop_loss": stop, "take_profit": target,
        })
        self._event("exit_armed", f"{side} break-even {be:.8g}, target {target:.8g}", break_even=be, target=target, stop=stop)

    async def _submit_entry(self, side: str, signal_price: float, receipt: list[dict], req: BacktestRequest, bar_ts: int) -> None:
        paper = await self._assert_paper()
        equity = float(paper.get("equity_usdt") or paper.get("cash_usdt") or 0.0)
        if equity <= 0:
            raise RuntimeError("Paper account equity is unavailable or non-positive")
        qty = (equity * req.leverage * (req.allocation_pct / 100.0)) / signal_price if signal_price > 0 else 0.0
        if qty <= 0:
            raise RuntimeError("Calculated paper order quantity is zero")
        next_layer = self.state.layers + 1
        client_order_id = f"terminal-{(self.state.session_id or 'session')[:8]}-{bar_ts}-{side}-{next_layer}"
        payload = {"symbol": req.symbol, "side": "buy" if side == "long" else "sell", "type": "market", "qty": qty, "qty_mode": "units", "leverage": req.leverage, "margin_mode": "cross", "client_order_id": client_order_id}
        self.state.pending_intent = {"bar_ts_ms": bar_ts, "side": side, "layer": next_layer, "qty": qty, "client_order_id": client_order_id}
        self._event("intent_pending", f"{side} layer {next_layer} {client_order_id}", receipt=receipt)
        await self._assert_paper()
        order = await self._json("POST", "/api/orders", json=payload)
        self.state.layers = next_layer
        self.state.bars_in_position = 0 if self.state.layers == 1 else self.state.bars_in_position
        self._event("entry_submitted", f"{side} layer {self.state.layers} qty={qty:.8g}", order=order, receipt=receipt, client_order_id=client_order_id)
        for _ in range(8):
            await self._assert_paper()
            pos = self._find_position(await self._positions(), req.symbol)
            if pos:
                self.state.position, self.state.pending_intent = pos, None
                self._checkpoint()
                await self._arm_exits(pos, req)
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("Paper order returned but position did not appear; pending intent retained for restart reconciliation")

    async def _close_for_timeout(self, pos: dict, req: BacktestRequest) -> None:
        await self._assert_paper()
        await self._json("POST", "/api/positions/close", json={"symbol": str(pos.get("symbol") or req.symbol), "side": str(pos.get("side")), "qty": None})
        self._event("timeout_close", f"closed after {self.state.bars_in_position} completed bars")
        self.state.position, self.state.layers, self.state.bars_in_position, self.state.pending_intent = None, 0, 0, None
        self._checkpoint()

    async def start(
        self,
        req: BacktestRequest,
        base_url: str | None,
        cookie: str,
        *,
        account_id: str | None = None,
        session_id: str | None = None,
        session_name: str | None = None,
    ) -> dict[str, Any]:
        if self._task and not self._task.done():
            raise RuntimeError("This paper session is already running")
        if not base_url:
            raise RuntimeError("Set EPINNOX_ONLINE_BASE_URL before starting PAPER")
        if not account_id:
            raise RuntimeError("Select a paper account before starting PAPER")
        self._req, self._base_url, self._cookie = req, base_url, cookie
        self._stop, self._shutdown_for_restart = asyncio.Event(), False
        self.state = PaperRuntimeState(
            session_id=session_id or str(uuid.uuid4()),
            name=(session_name or "").strip() or None,
            account_id=account_id,
            status="RUNNING",
            running=True,
            started_at_ms=int(time.time() * 1000),
        )
        await self._assert_paper()
        self._checkpoint()
        self._event("started", f"{req.symbol} {req.timeframe} {req.confirmation_policy}", account_id=account_id)
        self._task = asyncio.create_task(self._loop(), name=f"paper-{self.state.session_id}")
        return self.snapshot()

    async def recover_record(self, active: dict[str, Any], base_url: str | None, cookie: str = "") -> dict[str, Any]:
        if self._task and not self._task.done():
            return self.snapshot()
        raw_request = dict(active["request"] or {})
        account_id = str(raw_request.pop("_terminal_account_id", "") or "").strip() or None
        session_name = str(raw_request.pop("_terminal_session_name", "") or "").strip() or None
        self._req = BacktestRequest.model_validate(raw_request)
        self._base_url, self._cookie = base_url, cookie
        self._stop, self._shutdown_for_restart = asyncio.Event(), False
        self.state = PaperRuntimeState(
            session_id=active["session_id"],
            name=session_name,
            account_id=account_id,
            status="RECONCILING",
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
        if not base_url or not account_id or not cookie:
            self.state.running = False
            self.state.last_error = "Session recovery requires the authenticated Epinnox Online browser session; recovery is fail-closed"
            self._checkpoint("RECOVERY_REQUIRED")
            return self.snapshot()
        try:
            await self._assert_paper()
            pos = self._find_position(await self._positions(), self._req.symbol)
            self.state.position = pos
            if pos is None:
                if self.state.pending_intent:
                    raise RuntimeError("A pre-restart order intent is unresolved and no upstream position exists; refusing duplicate submission")
                self.state.layers, self.state.bars_in_position = 0, 0
            else:
                self.state.layers = max(1, self.state.layers)
                if self.state.pending_intent:
                    self._event("intent_reconciled", "pending pre-restart intent reconciled to authoritative upstream position", intent=self.state.pending_intent)
                    self.state.pending_intent = None
                await self._arm_exits(pos, self._req)
            self.state.recovered_count += 1
            self.state.last_error, self.state.running = None, True
            self._checkpoint("RECOVERED")
            self._event("recovered_after_restart", f"session recovered; upstream position={'present' if pos else 'flat'}")
            self._task = asyncio.create_task(self._loop(), name=f"paper-{self.state.session_id}")
        except Exception as exc:
            self.state.running, self.state.last_error = False, str(exc)
            self._checkpoint("RECOVERY_REQUIRED")
            self._event("recovery_required", str(exc))
        return self.snapshot()

    async def recover(self, base_url: str | None, cookie: str = "") -> dict[str, Any]:
        active = self.store.load_active_session()
        if not active:
            return self.snapshot()
        return await self.recover_record(active, base_url, cookie)

    async def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.state.running, self.state.pending_intent = False, None
        self._event("stopped", "paper live runner stopped; existing paper positions were left untouched")
        self._checkpoint("STOPPED")
        return self.snapshot()

    async def shutdown(self) -> None:
        if not self._task or self._task.done():
            return
        self._shutdown_for_restart, self.state.running = True, False
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._event("server_shutdown_checkpoint", "server shutdown checkpoint saved; session remains recoverable")
        self._checkpoint("RUNNING")

    async def _loop(self) -> None:
        assert self._req is not None
        req = self._req
        try:
            while not self._stop.is_set():
                try:
                    await self._assert_paper()
                    candles = await asyncio.to_thread(fetch_ohlcv, req.symbol, req.timeframe, max(250, min(req.limit, 1000)))
                    if len(candles) < 50:
                        raise RuntimeError("Not enough market history for live signal evaluation")
                    df, i = pd.DataFrame(candles), len(candles) - 2
                    bar_ts = int(df.ts_ms.iloc[i])
                    if self.state.last_bar_ts_ms == bar_ts:
                        await asyncio.sleep(2.0)
                        continue
                    self.state.last_bar_ts_ms, self.state.last_error = bar_ts, None
                    logic = build_entry_model(df, req.strategy, req.timeframe, req.manual_params, req.confirmations, req.confirmation_policy, req.confirmation_required, req.confirmation_window_bars)
                    await self._assert_paper()
                    pos = self._find_position(await self._positions(), req.symbol)
                    if pos is None:
                        self.state.position, self.state.layers, self.state.bars_in_position = None, 0, 0
                    else:
                        self.state.position, self.state.bars_in_position = pos, self.state.bars_in_position + 1
                        if req.max_bars_in_trade and self.state.bars_in_position >= req.max_bars_in_trade:
                            await self._close_for_timeout(pos, req)
                            await asyncio.sleep(1.0)
                            continue
                    self._checkpoint()
                    sig_side = "long" if req.direction in {"Both", "Long Only"} and bool(logic["long"].iloc[i]) else "short" if req.direction in {"Both", "Short Only"} and bool(logic["short"].iloc[i]) else None
                    if sig_side:
                        receipt = entry_receipt(logic, i, sig_side)
                        self.state.last_signal = {"ts_ms": bar_ts, "side": sig_side, "receipt": receipt}
                        self._checkpoint()
                        same_side = pos is not None and str(pos.get("side")) == sig_side
                        if pos is None or (same_side and self.state.layers < req.pyramiding):
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
            self._checkpoint("RUNNING" if self._shutdown_for_restart else "STOPPED" if self._stop.is_set() else "RECOVERY_REQUIRED")
