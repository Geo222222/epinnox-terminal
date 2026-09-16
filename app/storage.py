from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "epinnox_terminal.db"


class RuntimeStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_sessions (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    started_at_ms INTEGER,
                    updated_at_ms INTEGER NOT NULL,
                    last_bar_ts_ms INTEGER,
                    last_error TEXT,
                    last_signal_json TEXT,
                    position_json TEXT,
                    layers INTEGER NOT NULL DEFAULT 0,
                    bars_in_position INTEGER NOT NULL DEFAULT 0,
                    pending_intent_json TEXT,
                    recovered_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_paper_sessions_status
                ON paper_sessions(status, updated_at_ms DESC);

                CREATE TABLE IF NOT EXISTS paper_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    payload_json TEXT,
                    FOREIGN KEY(session_id) REFERENCES paper_sessions(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_paper_events_session
                ON paper_events(session_id, id DESC);

                CREATE TABLE IF NOT EXISTS named_presets (
                    name TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    payload_json TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                """
            )

    @staticmethod
    def _dump(value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _load(value: str | None) -> Any:
        if value is None:
            return None
        return json.loads(value)

    def save_session(self, session_id: str, *, status: str, request: dict[str, Any], started_at_ms: int | None,
                     last_bar_ts_ms: int | None, last_error: str | None, last_signal: Any,
                     position: Any, layers: int, bars_in_position: int, pending_intent: Any,
                     recovered_count: int = 0) -> None:
        now = int(time.time() * 1000)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_sessions(
                    session_id,status,request_json,started_at_ms,updated_at_ms,last_bar_ts_ms,last_error,
                    last_signal_json,position_json,layers,bars_in_position,pending_intent_json,recovered_count
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status=excluded.status,
                    request_json=excluded.request_json,
                    started_at_ms=excluded.started_at_ms,
                    updated_at_ms=excluded.updated_at_ms,
                    last_bar_ts_ms=excluded.last_bar_ts_ms,
                    last_error=excluded.last_error,
                    last_signal_json=excluded.last_signal_json,
                    position_json=excluded.position_json,
                    layers=excluded.layers,
                    bars_in_position=excluded.bars_in_position,
                    pending_intent_json=excluded.pending_intent_json,
                    recovered_count=excluded.recovered_count
                """,
                (
                    session_id,status,self._dump(request),started_at_ms,now,last_bar_ts_ms,last_error,
                    self._dump(last_signal),self._dump(position),layers,bars_in_position,
                    self._dump(pending_intent),recovered_count,
                ),
            )

    def supersede_active_sessions(self, keep_session_id: str | None = None) -> int:
        now = int(time.time() * 1000)
        with self._lock, self._connect() as conn:
            if keep_session_id:
                cur = conn.execute(
                    """
                    UPDATE paper_sessions
                    SET status='SUPERSEDED', updated_at_ms=?
                    WHERE status IN ('RUNNING','RECONCILING','RECOVERED','RECOVERY_REQUIRED')
                      AND session_id<>?
                    """,
                    (now, keep_session_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE paper_sessions
                    SET status='SUPERSEDED', updated_at_ms=?
                    WHERE status IN ('RUNNING','RECONCILING','RECOVERED','RECOVERY_REQUIRED')
                    """,
                    (now,),
                )
            return cur.rowcount

    def load_active_session(self) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM paper_sessions
                WHERE status IN ('RUNNING','RECONCILING','RECOVERED','RECOVERY_REQUIRED')
                ORDER BY updated_at_ms DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM paper_sessions WHERE session_id=?", (session_id,)).fetchone()
        return None if row is None else self._row_to_session(row)

    def _row_to_session(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "status": row["status"],
            "request": self._load(row["request_json"]),
            "started_at_ms": row["started_at_ms"],
            "updated_at_ms": row["updated_at_ms"],
            "last_bar_ts_ms": row["last_bar_ts_ms"],
            "last_error": row["last_error"],
            "last_signal": self._load(row["last_signal_json"]),
            "position": self._load(row["position_json"]),
            "layers": row["layers"],
            "bars_in_position": row["bars_in_position"],
            "pending_intent": self._load(row["pending_intent_json"]),
            "recovered_count": row["recovered_count"],
        }

    def add_event(self, session_id: str, ts_ms: int, kind: str, detail: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO paper_events(session_id,ts_ms,kind,detail,payload_json) VALUES(?,?,?,?,?)",
                (session_id, ts_ms, kind, detail, self._dump(payload)),
            )

    def recent_events(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT ts_ms,kind,detail,payload_json FROM paper_events WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, max(1, min(limit, 1000))),
            ).fetchall()
        out = []
        for row in reversed(rows):
            payload = self._load(row["payload_json"]) or {}
            out.append({"ts_ms": row["ts_ms"], "kind": row["kind"], "detail": row["detail"], **payload})
        return out

    def list_presets(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT name,schema_version,payload_json,updated_at_ms FROM named_presets ORDER BY name").fetchall()
        return [
            {"name": r["name"], "schema_version": r["schema_version"], "payload": self._load(r["payload_json"]), "updated_at_ms": r["updated_at_ms"]}
            for r in rows
        ]

    def save_preset(self, name: str, payload: dict[str, Any], schema_version: int = 1) -> dict[str, Any]:
        now = int(time.time() * 1000)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO named_presets(name,schema_version,payload_json,updated_at_ms) VALUES(?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET schema_version=excluded.schema_version,payload_json=excluded.payload_json,updated_at_ms=excluded.updated_at_ms
                """,
                (name, schema_version, self._dump(payload), now),
            )
        return {"name": name, "schema_version": schema_version, "payload": payload, "updated_at_ms": now}

    def delete_preset(self, name: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM named_presets WHERE name=?", (name,))
            return cur.rowcount > 0


runtime_store = RuntimeStore()
