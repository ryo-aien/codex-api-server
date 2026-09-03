from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class ApiKeyNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ApiKeyRecord:
    id: int
    client_db_id: int
    key_id: str
    key_hash: str
    enabled: bool
    created_at: str
    last_used_at: str | None
    expires_at: str | None
    revoked_at: str | None


@dataclass(frozen=True)
class ApiKeyLookupResult:
    api_key: ApiKeyRecord
    client_id: str
    display_name: str | None
    role: str
    client_enabled: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_record(row: sqlite3.Row) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=row["id"],
        client_db_id=row["client_db_id"],
        key_id=row["key_id"],
        key_hash=row["key_hash"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


def create_api_key(
    conn: sqlite3.Connection,
    client_db_id: int,
    key_id: str,
    key_hash: str,
    expires_in_days: int | None = None,
) -> ApiKeyRecord:
    now = _now()
    expires_at = None
    if expires_in_days is not None:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat()

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO api_keys (client_db_id, key_id, key_hash, enabled, created_at, expires_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (client_db_id, key_id, key_hash, now, expires_at),
        )
    row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_record(row)


def find_by_hash(conn: sqlite3.Connection, key_hash: str) -> ApiKeyLookupResult | None:
    row = conn.execute(
        """
        SELECT api_keys.*, clients.client_id AS c_client_id,
               clients.display_name AS c_display_name,
               clients.role AS c_role,
               clients.enabled AS c_enabled
        FROM api_keys
        JOIN clients ON clients.id = api_keys.client_db_id
        WHERE api_keys.key_hash = ?
        """,
        (key_hash,),
    ).fetchone()
    if row is None:
        return None
    return ApiKeyLookupResult(
        api_key=_row_to_record(row),
        client_id=row["c_client_id"],
        display_name=row["c_display_name"],
        role=row["c_role"],
        client_enabled=bool(row["c_enabled"]),
    )


def touch_last_used(conn: sqlite3.Connection, key_id: str) -> None:
    with conn:
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
            (_now(), key_id),
        )


def list_by_client(conn: sqlite3.Connection, client_db_id: int) -> list[ApiKeyRecord]:
    rows = conn.execute(
        "SELECT * FROM api_keys WHERE client_db_id = ? ORDER BY created_at ASC",
        (client_db_id,),
    ).fetchall()
    return [_row_to_record(row) for row in rows]


def get_by_key_id(conn: sqlite3.Connection, key_id: str) -> ApiKeyRecord | None:
    row = conn.execute("SELECT * FROM api_keys WHERE key_id = ?", (key_id,)).fetchone()
    return _row_to_record(row) if row is not None else None


def revoke(conn: sqlite3.Connection, key_id: str) -> ApiKeyRecord:
    existing = get_by_key_id(conn, key_id)
    if existing is None:
        raise ApiKeyNotFoundError(f"key_id '{key_id}' not found")
    with conn:
        conn.execute(
            "UPDATE api_keys SET enabled = 0, revoked_at = ? WHERE key_id = ?",
            (_now(), key_id),
        )
    return get_by_key_id(conn, key_id)  # type: ignore[return-value]


def set_enabled(conn: sqlite3.Connection, key_id: str, enabled: bool) -> ApiKeyRecord:
    existing = get_by_key_id(conn, key_id)
    if existing is None:
        raise ApiKeyNotFoundError(f"key_id '{key_id}' not found")
    with conn:
        conn.execute(
            "UPDATE api_keys SET enabled = ? WHERE key_id = ?",
            (1 if enabled else 0, key_id),
        )
    return get_by_key_id(conn, key_id)  # type: ignore[return-value]
