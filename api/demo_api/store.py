"""Saved runs: every live run is kept so it can be replayed from a link.

A single SQLite file (DEMO_DB, default runs.db next to the app; on a host, put it on a
volume). It stores the run's own events and nothing about the visitor: no address, no
headers. The oldest runs are dropped past DEMO_KEEP_RUNS (default 5000).
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    option TEXT NOT NULL,
    created_at REAL NOT NULL,
    cost_usd REAL NOT NULL DEFAULT 0,
    events TEXT NOT NULL
)
"""


class RunStore:
    def __init__(self, path: str | None = None, keep: int | None = None) -> None:
        self.path = path or os.environ.get("DEMO_DB", "runs.db")
        self.keep = keep if keep is not None else int(os.environ.get("DEMO_KEEP_RUNS", "5000"))
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @staticmethod
    def new_id() -> str:
        return secrets.token_urlsafe(8)

    def save(
        self, run_id: str, scenario: str, option: str, events: list[dict[str, Any]], cost: float
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO runs (id, scenario, option, created_at, cost_usd, events)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, scenario, option, time.time(), cost, json.dumps(events)),
            )
            db.execute(
                "DELETE FROM runs WHERE id NOT IN"
                " (SELECT id FROM runs ORDER BY created_at DESC LIMIT ?)",
                (self.keep,),
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id, scenario, option, created_at, cost_usd, events FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "scenario": row[1],
            "option": row[2],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[3])),
            "cost_usd": row[4],
            "events": json.loads(row[5]),
        }

    def count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
