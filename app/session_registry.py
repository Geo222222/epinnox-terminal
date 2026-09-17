from __future__ import annotations

import asyncio
from typing import Any

from .models import BacktestRequest
from .paper_live import PaperLiveManager
from .storage import ACTIVE_SESSION_STATUSES, RuntimeStore, runtime_store


class SessionConflict(RuntimeError):
    pass


class SessionNotFound(RuntimeError):
    pass


def _record_identity(record: dict[str, Any]) -> tuple[str | None, str | None]:
    raw = dict(record.get("request") or {})
    account_id = str(raw.get("_terminal_account_id") or "").strip() or None
    symbol = str(raw.get("symbol") or "").strip() or None
    return account_id, symbol


class PaperSessionRegistry:
    """Owns independent durable paper runners.

    Current Epinnox Online routing is browser-session/account-context based, so
    concurrent execution is safe only when all running sessions share the same
    active account and each session owns a different instrument. This registry
    makes that constraint explicit until upstream APIs accept account_id on each
    execution mutation.
    """

    def __init__(self, store: RuntimeStore = runtime_store) -> None:
        self.store = store
        self._managers: dict[str, PaperLiveManager] = {}
        self._lock = asyncio.Lock()

    def _persisted_active(self) -> list[dict[str, Any]]:
        return self.store.load_active_sessions()

    def _active_records_excluding(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self._persisted_active() if r["session_id"] != session_id]

    def _assert_available(self, account_id: str, symbol: str, *, exclude_session_id: str | None = None) -> None:
        for record in self._active_records_excluding(exclude_session_id):
            other_account, other_symbol = _record_identity(record)
            if other_account and other_account != account_id:
                raise SessionConflict(
                    "Another active paper session is bound to a different Epinnox Online account. "
                    "Concurrent multi-account execution stays fail-closed until upstream order APIs are account-scoped."
                )
            if other_account == account_id and other_symbol and other_symbol.upper() == symbol.upper():
                raise SessionConflict(
                    f"Account {account_id} already has an active session owning {symbol}. "
                    "Only one strategy owner per account + instrument is allowed."
                )

    async def start(
        self,
        req: BacktestRequest,
        base_url: str | None,
        cookie: str,
        *,
        account_id: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            self._assert_available(account_id, req.symbol)
            manager = PaperLiveManager(self.store)
            snapshot = await manager.start(
                req,
                base_url,
                cookie,
                account_id=account_id,
                session_name=name,
            )
            session_id = str(snapshot["session_id"])
            self._managers[session_id] = manager
            return self._manager_snapshot(manager)

    async def recover(self, session_id: str, base_url: str | None, cookie: str) -> dict[str, Any]:
        async with self._lock:
            record = self.store.get_session(session_id)
            if record is None:
                raise SessionNotFound(f"Paper session {session_id} was not found")
            raw = dict(record.get("request") or {})
            account_id = str(raw.get("_terminal_account_id") or "").strip()
            symbol = str(raw.get("symbol") or "").strip()
            if not account_id or not symbol:
                raise SessionConflict("Persisted session is missing its account or symbol ownership identity")
            self._assert_available(account_id, symbol, exclude_session_id=session_id)
            manager = self._managers.get(session_id) or PaperLiveManager(self.store)
            await manager.recover_record(record, base_url, cookie)
            self._managers[session_id] = manager
            return self._manager_snapshot(manager)

    async def stop(self, session_id: str) -> dict[str, Any]:
        async with self._lock:
            manager = self._managers.get(session_id)
            if manager is not None:
                await manager.stop()
                snapshot = self._manager_snapshot(manager)
                self._managers.pop(session_id, None)
                return snapshot
            record = self.store.get_session(session_id)
            if record is None:
                raise SessionNotFound(f"Paper session {session_id} was not found")
            self.store.mark_session_status(session_id, "STOPPED", None)
            record = self.store.get_session(session_id) or record
            return self._record_snapshot(record)

    @staticmethod
    def _clean_request(raw_request: dict[str, Any] | None) -> tuple[dict[str, Any], str | None, str | None]:
        raw = dict(raw_request or {})
        account_id = raw.pop("_terminal_account_id", None)
        name = raw.pop("_terminal_session_name", None)
        return raw, account_id, name

    def _manager_snapshot(self, manager: PaperLiveManager) -> dict[str, Any]:
        snapshot = manager.snapshot()
        req = manager.request
        if req is not None:
            snapshot["request"] = req.model_dump(mode="json")
        else:
            snapshot["request"] = None
        return snapshot

    def _record_snapshot(self, record: dict[str, Any]) -> dict[str, Any]:
        raw, account_id, name = self._clean_request(record.get("request"))
        return {
            "session_id": record["session_id"],
            "name": name,
            "environment": "PAPER",
            "account_id": account_id,
            "symbol": raw.get("symbol"),
            "timeframe": raw.get("timeframe"),
            "strategy": raw.get("strategy"),
            "request": raw,
            "status": record["status"],
            "running": False,
            "started_at_ms": record["started_at_ms"],
            "updated_at_ms": record["updated_at_ms"],
            "last_bar_ts_ms": record["last_bar_ts_ms"],
            "last_error": record["last_error"],
            "last_signal": record["last_signal"],
            "position": record["position"],
            "layers": record["layers"],
            "bars_in_position": record["bars_in_position"],
            "pending_intent": record["pending_intent"],
            "recovered_count": record["recovered_count"],
            "recoverable": record["status"] in ACTIVE_SESSION_STATUSES,
            "events": self.store.recent_events(record["session_id"], 50),
        }

    def get(self, session_id: str) -> dict[str, Any]:
        manager = self._managers.get(session_id)
        if manager is not None:
            return self._manager_snapshot(manager)
        record = self.store.get_session(session_id)
        if record is None:
            raise SessionNotFound(f"Paper session {session_id} was not found")
        return self._record_snapshot(record)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        records = self.store.list_sessions(limit)
        out: list[dict[str, Any]] = []
        for record in records:
            manager = self._managers.get(record["session_id"])
            out.append(self._manager_snapshot(manager) if manager is not None else self._record_snapshot(record))
        return out

    def active(self) -> list[dict[str, Any]]:
        return [x for x in self.list(1000) if x.get("status") in ACTIVE_SESSION_STATUSES]

    async def shutdown(self) -> None:
        managers = list(self._managers.values())
        if managers:
            await asyncio.gather(*(m.shutdown() for m in managers), return_exceptions=True)
        self._managers.clear()


paper_sessions = PaperSessionRegistry()
