"""
GitHub integration — local persistence (SQLite)
===============================================
A tiny SQLite database under ``~/.ambilight/github.db`` that holds:

* **seen** — de-dup keys for events already processed (so a re-poll of the same
  inbox item / workflow run doesn't re-flash the lights).
* **events** — a bounded ring buffer of recent normalized events for the UI's
  "Recent Events" list.
* **poll_state** — per-source ``ETag`` / ``Last-Modified`` cursors so polls are
  conditional requests (304 = nothing new, and don't count against rate limit).
* **cache** — last-known account / orgs / repos JSON so the UI has something to
  show before the first live fetch.

Tokens are **never** stored here — they live in the OS keyring (see
:mod:`secrets_store`). The DB is opened with ``check_same_thread=False`` and
guarded by a lock so the poll loop and API handlers can share it.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...paths import user_data_dir
from .models import GithubEvent

logger = logging.getLogger(__name__)

_RECENT_CAP = 200  # rows kept in the events ring buffer


class GithubStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else (user_data_dir() / "github.db")
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self._path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS seen (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
                CREATE TABLE IF NOT EXISTS poll_state (
                    key TEXT PRIMARY KEY,
                    etag TEXT,
                    last_modified TEXT,
                    last_poll REAL
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    json TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                """
            )
            self._db.commit()

    # --- de-dup ----------------------------------------------------------
    def mark_seen(self, event_id: str) -> bool:
        """Record *event_id*; return ``True`` if it was new (i.e. process it)."""
        if not event_id:
            return False
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO seen(id, ts) VALUES(?, ?)", (event_id, time.time())
                )
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def prune_seen(self, older_than_s: float = 7 * 24 * 3600) -> None:
        cutoff = time.time() - older_than_s
        with self._lock:
            self._db.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
            self._db.commit()

    # --- recent events ring buffer --------------------------------------
    def add_event(self, event: GithubEvent) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO events(id, ts, json) VALUES(?, ?, ?)",
                (event.id, event.timestamp, json.dumps(event.to_dict())),
            )
            # Trim to the newest _RECENT_CAP rows.
            self._db.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY ts DESC LIMIT ?)",
                (_RECENT_CAP,),
            )
            self._db.commit()

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT json FROM events ORDER BY ts DESC LIMIT ?", (int(limit),)
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                out.append(json.loads(row["json"]))
            except Exception:
                continue
        return out

    # --- conditional-request cursors ------------------------------------
    def get_poll_state(self, key: str) -> Dict[str, Any]:
        with self._lock:
            row = self._db.execute(
                "SELECT etag, last_modified, last_poll FROM poll_state WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return {"etag": None, "last_modified": None, "last_poll": 0.0}
        return {
            "etag": row["etag"],
            "last_modified": row["last_modified"],
            "last_poll": row["last_poll"] or 0.0,
        }

    def set_poll_state(self, key: str, etag: Optional[str] = None,
                       last_modified: Optional[str] = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO poll_state(key, etag, last_modified, last_poll) "
                "VALUES(?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "etag=excluded.etag, last_modified=excluded.last_modified, "
                "last_poll=excluded.last_poll",
                (key, etag, last_modified, time.time()),
            )
            self._db.commit()

    # --- small JSON cache (accounts / orgs / repos) ----------------------
    def set_cache(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO cache(key, json, ts) VALUES(?, ?, ?)",
                (key, json.dumps(value), time.time()),
            )
            self._db.commit()

    def get_cache(self, key: str) -> Optional[Any]:
        with self._lock:
            row = self._db.execute(
                "SELECT json FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["json"])
        except Exception:
            return None

    def close(self) -> None:
        with self._lock:
            try:
                self._db.close()
            except Exception:
                pass
