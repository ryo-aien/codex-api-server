from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class AuditLogEntry:
    timestamp: str
    request_id: str | None = None
    client_id: str | None = None
    key_id: str | None = None
    action: str = ""
    method: str | None = None
    path: str | None = None
    repository: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    status_code: int | None = None
    duration_ms: int | None = None
    remote_ip: str | None = None
    user_agent: str | None = None
    prompt_chars: int | None = None
    result_status: str | None = None
    error_code: str | None = None


def insert_audit_log(conn: sqlite3.Connection, entry: AuditLogEntry) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO audit_logs (
                timestamp, request_id, client_id, key_id, action, method, path,
                repository, thread_id, turn_id, status_code, duration_ms,
                remote_ip, user_agent, prompt_chars, result_status, error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp,
                entry.request_id,
                entry.client_id,
                entry.key_id,
                entry.action,
                entry.method,
                entry.path,
                entry.repository,
                entry.thread_id,
                entry.turn_id,
                entry.status_code,
                entry.duration_ms,
                entry.remote_ip,
                entry.user_agent,
                entry.prompt_chars,
                entry.result_status,
                entry.error_code,
            ),
        )


def new_entry(action: str, **kwargs) -> AuditLogEntry:
    return AuditLogEntry(timestamp=datetime.now(timezone.utc).isoformat(), action=action, **kwargs)


def list_audit_logs(
    conn: sqlite3.Connection,
    *,
    client_id: str | None = None,
    repository: str | None = None,
    limit: int = 100,
) -> list[sqlite3.Row]:
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params: list = []

    if client_id is not None:
        query += " AND client_id = ?"
        params.append(client_id)

    if repository is not None:
        query += " AND repository = ?"
        params.append(repository)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    return conn.execute(query, params).fetchall()
