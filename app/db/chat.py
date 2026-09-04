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
    first_message_preview: str | None


PREVIEW_MAX_CHARS = 30


def _make_preview(prompt: str) -> str:
    """First 30 chars of the opening message, for display in the list."""
    return prompt.strip()[:PREVIEW_MAX_CHARS]


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
        first_message_preview=row["first_message_preview"],
    )


def create_conversation(
    conn: sqlite3.Connection,
    conversation_id: str,
    owner_client_id: str,
    first_message: str = "",
) -> ConversationRecord:
    now = _now()
    preview = _make_preview(first_message) if first_message else None
    with conn:
        conn.execute(
            """
            INSERT INTO chat_conversations
                (conversation_id, owner_client_id, created_at, updated_at, archived,
                 first_message_preview)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (conversation_id, owner_client_id, now, now, preview),
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


def delete_conversation(conn: sqlite3.Connection, conversation_id: str) -> None:
    """Hard-delete a conversation row (ownership is checked by the caller)."""
    with conn:
        conn.execute(
            "DELETE FROM chat_conversations WHERE conversation_id = ?",
            (conversation_id,),
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
