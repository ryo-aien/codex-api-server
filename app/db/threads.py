from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


class ThreadNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ThreadRecord:
    thread_id: str
    owner_client_id: str
    repository: str
    created_at: str
    updated_at: str
    archived: bool
    last_turn_id: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_record(row: sqlite3.Row) -> ThreadRecord:
    return ThreadRecord(
        thread_id=row["thread_id"],
        owner_client_id=row["owner_client_id"],
        repository=row["repository"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived=bool(row["archived"]),
        last_turn_id=row["last_turn_id"],
    )


def create_thread(
    conn: sqlite3.Connection,
    thread_id: str,
    owner_client_id: str,
    repository: str,
) -> ThreadRecord:
    now = _now()
    with conn:
        conn.execute(
            """
            INSERT INTO codex_threads (thread_id, owner_client_id, repository, created_at, updated_at, archived)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (thread_id, owner_client_id, repository, now, now),
        )
    return get_thread(conn, thread_id)  # type: ignore[return-value]


def get_thread(conn: sqlite3.Connection, thread_id: str) -> ThreadRecord | None:
    row = conn.execute(
        "SELECT * FROM codex_threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    return _row_to_record(row) if row is not None else None


def touch_thread(conn: sqlite3.Connection, thread_id: str, last_turn_id: str | None) -> None:
    with conn:
        conn.execute(
            "UPDATE codex_threads SET updated_at = ?, last_turn_id = ? WHERE thread_id = ?",
            (_now(), last_turn_id, thread_id),
        )


def archive_thread(conn: sqlite3.Connection, thread_id: str) -> ThreadRecord:
    existing = get_thread(conn, thread_id)
    if existing is None:
        raise ThreadNotFoundError(f"thread_id '{thread_id}' not found")
    with conn:
        conn.execute(
            "UPDATE codex_threads SET archived = 1, updated_at = ? WHERE thread_id = ?",
            (_now(), thread_id),
        )
    return get_thread(conn, thread_id)  # type: ignore[return-value]


def list_threads_for_owner(
    conn: sqlite3.Connection,
    owner_client_id: str,
    *,
    archived: bool | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[ThreadRecord]:
    query = "SELECT * FROM codex_threads WHERE owner_client_id = ?"
    params: list = [owner_client_id]

    if archived is not None:
        query += " AND archived = ?"
        params.append(1 if archived else 0)

    if cursor is not None:
        query += " AND thread_id < ?"
        params.append(cursor)

    query += " ORDER BY thread_id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [_row_to_record(row) for row in rows]
