from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .storage import DB_PATH


class ScanStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS opportunity_scans (
                    scan_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    started_at_ms INTEGER NOT NULL,
                    completed_at_ms INTEGER NOT NULL,
                    request_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opportunity_scans_created
                    ON opportunity_scans(created_at_ms DESC);
                """
            )

    def save(self, result: dict[str, Any]) -> None:
        now = int(time.time() * 1000)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO opportunity_scans(
                    scan_id,objective,started_at_ms,completed_at_ms,request_json,summary_json,result_json,created_at_ms
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    result["scan_id"], result["objective"], result["started_at_ms"], result["completed_at_ms"],
                    json.dumps(result["request"], separators=(",", ":")),
                    json.dumps(result["summary"], separators=(",", ":")),
                    json.dumps(result, separators=(",", ":")), now,
                ),
            )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT scan_id,objective,started_at_ms,completed_at_ms,summary_json,created_at_ms FROM opportunity_scans ORDER BY created_at_ms DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [
            {
                "scan_id": row["scan_id"],
                "objective": row["objective"],
                "started_at_ms": row["started_at_ms"],
                "completed_at_ms": row["completed_at_ms"],
                "summary": json.loads(row["summary_json"]),
                "created_at_ms": row["created_at_ms"],
            }
            for row in rows
        ]

    def get(self, scan_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT result_json FROM opportunity_scans WHERE scan_id=?", (scan_id,)).fetchone()
        return None if row is None else json.loads(row["result_json"])


scan_store = ScanStore()
