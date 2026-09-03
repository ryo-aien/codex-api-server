from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path


def connect(database_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with the pragmas this application relies on."""
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


class Database:
    """Thin wrapper that serializes SQLite access off the event loop.

    A single writer connection is reused and all calls are dispatched via
    ``asyncio.to_thread`` combined with a lock, so we never hold the event
    loop hostage during a query and never hand the same sqlite3.Connection
    to two threads concurrently.
    """

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    def connect_sync(self) -> None:
        if self._conn is None:
            self._conn = connect(self._database_path)

    @property
    def raw(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def run(self, fn, *args, **kwargs):
        """Run a synchronous function against the connection in a worker thread."""
        async with self._lock:
            return await asyncio.to_thread(fn, self.raw, *args, **kwargs)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
