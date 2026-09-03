from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
VALID_ROLES = {"user", "admin"}


class DuplicateClientError(Exception):
    pass


class InvalidClientIdError(Exception):
    pass


class InvalidRoleError(Exception):
    pass


class ClientNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ClientRecord:
    id: int
    client_id: str
    display_name: str | None
    role: str
    enabled: bool
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_record(row: sqlite3.Row) -> ClientRecord:
    return ClientRecord(
        id=row["id"],
        client_id=row["client_id"],
        display_name=row["display_name"],
        role=row["role"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def validate_client_id(client_id: str) -> None:
    if not CLIENT_ID_PATTERN.match(client_id):
        raise InvalidClientIdError(
            "client_id must match ^[A-Za-z0-9._-]{1,64}$"
        )


def create_client(
    conn: sqlite3.Connection,
    client_id: str,
    display_name: str | None,
    role: str = "user",
) -> ClientRecord:
    validate_client_id(client_id)
    if role not in VALID_ROLES:
        raise InvalidRoleError(f"role must be one of {sorted(VALID_ROLES)}")

    now = _now()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO clients (client_id, display_name, role, enabled, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (client_id, display_name, role, now, now),
            )
    except sqlite3.IntegrityError as exc:
        raise DuplicateClientError(f"client_id '{client_id}' already exists") from exc

    return get_client_by_db_id(conn, cursor.lastrowid)


def get_client_by_db_id(conn: sqlite3.Connection, db_id: int) -> ClientRecord:
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (db_id,)).fetchone()
    if row is None:
        raise ClientNotFoundError(f"client db id {db_id} not found")
    return _row_to_record(row)


def get_client(conn: sqlite3.Connection, client_id: str) -> ClientRecord | None:
    row = conn.execute("SELECT * FROM clients WHERE client_id = ?", (client_id,)).fetchone()
    return _row_to_record(row) if row is not None else None


def list_clients(conn: sqlite3.Connection) -> list[ClientRecord]:
    rows = conn.execute("SELECT * FROM clients ORDER BY created_at ASC").fetchall()
    return [_row_to_record(row) for row in rows]


def set_enabled(conn: sqlite3.Connection, client_id: str, enabled: bool) -> ClientRecord:
    existing = get_client(conn, client_id)
    if existing is None:
        raise ClientNotFoundError(f"client_id '{client_id}' not found")

    with conn:
        conn.execute(
            "UPDATE clients SET enabled = ?, updated_at = ? WHERE client_id = ?",
            (1 if enabled else 0, _now(), client_id),
        )
    return get_client(conn, client_id)  # type: ignore[return-value]
