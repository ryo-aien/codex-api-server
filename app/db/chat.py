from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


class ConversationNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    owner_client_id: str
    created_at: str
    updated_at: str
    archived: bool
    last_turn_id: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_record(row: sqlite3.Row) -> ConversationRecord:
    return ConversationRecord(
        conversation_id=row["conversation_id"],
        owner_client_id=row["owner_client_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived=bool(row["archived"]),
        last_turn_id=row["last_turn_id"],
    )


def create_conversation(
    conn: sqlite3.Connection, conversation_id: str, owner_client_id: str
) -> ConversationRecord:
    now = _now()
    with conn:
        conn.execute(
            """
            INSERT INTO chat_conversations
                (conversation_id, owner_client_id, created_at, updated_at, archived)
            VALUES (?, ?, ?, ?, 0)
            """,
            (conversation_id, owner_client_id, now, now),
        )
    return get_conversation(conn, conversation_id)  # type: ignore[return-value]


def get_conversation(
    conn: sqlite3.Connection, conversation_id: str
) -> ConversationRecord | None:
    row = conn.execute(
        "SELECT * FROM chat_conversations WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    return _row_to_record(row) if row is not None else None


def touch_conversation(
    conn: sqlite3.Connection, conversation_id: str, last_turn_id: str | None
) -> None:
    with conn:
        conn.execute(
            "UPDATE chat_conversations SET updated_at = ?, last_turn_id = ? WHERE conversation_id = ?",
            (_now(), last_turn_id, conversation_id),
        )


def list_conversations_for_owner(
    conn: sqlite3.Connection,
    owner_client_id: str,
    *,
    archived: bool | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[ConversationRecord]:
    query = "SELECT * FROM chat_conversations WHERE owner_client_id = ?"
    params: list = [owner_client_id]

    if archived is not None:
        query += " AND archived = ?"
        params.append(1 if archived else 0)

    if cursor is not None:
        query += " AND conversation_id < ?"
        params.append(cursor)

    query += " ORDER BY conversation_id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [_row_to_record(row) for row in rows]
